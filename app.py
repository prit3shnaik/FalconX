"""
FalconX OSINT Dashboard
Palantir-style link analysis graph for Zeeschuimer .ndjson Twitter/X data.
Stack: Streamlit + Neo4j (AuraDB) + streamlit-cytoscapejs
"""

import json
import re
import streamlit as st
from neo4j import GraphDatabase
from streamlit_cytoscapejs import st_cytoscapejs

# ─── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FalconX OSINT Dashboard",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS (Palantir-style dark UI) ────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');

  html, body, [class*="css"] {
    font-family: 'Rajdhani', sans-serif;
    background-color: #080d14;
    color: #c8d6e5;
  }
  .stApp { background-color: #080d14; }

  /* Header */
  .falcon-header {
    display: flex; align-items: center; gap: 14px;
    padding: 18px 0 10px 0;
    border-bottom: 1px solid #1a2a3a;
    margin-bottom: 22px;
  }
  .falcon-header h1 {
    font-family: 'Rajdhani', sans-serif;
    font-size: 2rem; font-weight: 700;
    color: #e8f4fd; margin: 0; letter-spacing: 2px;
  }
  .falcon-header .subtitle {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.72rem; color: #4a90b8; margin-top: 2px;
    letter-spacing: 1px;
  }
  .badge {
    background: #0f2236; border: 1px solid #1e4060;
    color: #4ab8ff; padding: 3px 10px; border-radius: 3px;
    font-size: 0.7rem; font-family: 'Share Tech Mono', monospace;
    letter-spacing: 1px;
  }

  /* Stat cards */
  .stat-grid { display: flex; gap: 14px; margin-bottom: 20px; }
  .stat-card {
    flex: 1; background: #0d1b2a; border: 1px solid #1a2e42;
    border-radius: 4px; padding: 14px 18px;
  }
  .stat-card .val {
    font-size: 1.8rem; font-weight: 700; color: #4ab8ff;
    font-family: 'Share Tech Mono', monospace;
  }
  .stat-card .lbl {
    font-size: 0.72rem; color: #5a7a9a; letter-spacing: 1px; margin-top: 2px;
  }

  /* Upload zone */
  .upload-zone {
    border: 1px dashed #1e4060; background: #0a1622;
    border-radius: 6px; padding: 28px; text-align: center;
    color: #4a7090; margin-bottom: 20px;
  }

  /* Sidebar */
  [data-testid="stSidebar"] {
    background: #0a1420 !important;
    border-right: 1px solid #1a2a3a;
  }
  [data-testid="stSidebar"] * { color: #c8d6e5 !important; }

  /* Tweet detail card */
  .tweet-card {
    background: #0d1b2a; border-left: 3px solid #4ab8ff;
    padding: 16px; border-radius: 0 4px 4px 0; margin-top: 12px;
    font-family: 'Share Tech Mono', monospace; font-size: 0.82rem;
    line-height: 1.6; color: #a8c8e8;
  }
  .tweet-meta { color: #4a7090; font-size: 0.72rem; margin-bottom: 8px; }

  /* Status bar */
  .status-bar {
    background: #0a1622; border: 1px solid #1a2e42;
    padding: 8px 14px; border-radius: 3px; margin-bottom: 14px;
    font-family: 'Share Tech Mono', monospace; font-size: 0.72rem;
    color: #3a7a9a; display: flex; gap: 20px;
  }
  .status-ok { color: #2ecc71; }
  .status-err { color: #e74c3c; }

  /* Divider */
  hr { border-color: #1a2a3a; }

  /* Section label */
  .section-label {
    font-size: 0.65rem; letter-spacing: 2px; color: #3a6a8a;
    text-transform: uppercase; margin-bottom: 8px;
    font-family: 'Share Tech Mono', monospace;
  }

  /* Streamlit button override */
  .stButton > button {
    background: #0f2236; border: 1px solid #1e4060;
    color: #4ab8ff; font-family: 'Rajdhani', sans-serif;
    font-weight: 600; letter-spacing: 1px; border-radius: 3px;
  }
  .stButton > button:hover {
    background: #1a3a54; border-color: #4ab8ff;
  }
</style>
""", unsafe_allow_html=True)

# ─── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="falcon-header">
  <div>
    <h1>🦅 FALCONX</h1>
    <div class="subtitle">OSINT LINK ANALYSIS DASHBOARD &nbsp;|&nbsp; ZEESCHUIMER INGEST</div>
  </div>
  <div style="margin-left:auto">
    <span class="badge">NEO4J AURADB</span>&nbsp;
    <span class="badge">CYTOSCAPE</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ─── Neo4j Connection ────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_driver():
    uri = st.secrets["NEO4J_URI"]
    user = st.secrets["NEO4J_USERNAME"]
    pw = st.secrets["NEO4J_PASSWORD"]
    return GraphDatabase.driver(uri, auth=(user, pw))


def test_connection():
    try:
        drv = get_driver()
        with drv.session() as s:
            s.run("RETURN 1")
        return True, None
    except Exception as e:
        return False, str(e)


# ─── Parsing Logic ───────────────────────────────────────────────────────────────
def safe_get(d: dict, *keys, default=None):
    """Safely traverse nested dicts."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, {})
    return d if d != {} else default


def extract_hashtags(entities: dict) -> list[str]:
    tags = []
    if not entities:
        return tags
    for ht in entities.get("hashtags", []):
        tag = ht.get("text") or ht.get("tag")
        if tag:
            tags.append(tag.lower())
    return list(set(tags))


def parse_ndjson(raw_bytes: bytes) -> list[dict]:
    """Parse Zeeschuimer .ndjson → list of tweet dicts."""
    records = []
    for line in raw_bytes.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        data = obj.get("data", obj)  # Zeeschuimer wraps in {"data": ...}

        # ── Tweet ID
        tweet_id = safe_get(data, "legacy", "id_str") or safe_get(data, "id_str", default="")

        # ── Content: note_tweet first, fallback to legacy.full_text
        content = safe_get(
            data,
            "note_tweet", "note_tweet_results", "result", "text"
        ) or safe_get(data, "legacy", "full_text") or ""

        # ── Screen name
        screen_name = (
            safe_get(data, "core", "user_results", "result", "core", "screen_name")
            or safe_get(data, "core", "user_results", "result", "legacy", "screen_name")
            or ""
        )

        # ── Hashtags from legacy entities + note_tweet entities
        legacy_entities = safe_get(data, "legacy", "entities", default={})
        note_entities = safe_get(
            data, "note_tweet", "note_tweet_results", "result", "entity_set", default={}
        )
        hashtags = list(set(extract_hashtags(legacy_entities) + extract_hashtags(note_entities)))

        if not tweet_id or not screen_name:
            continue

        records.append({
            "tweet_id": tweet_id,
            "content": content,
            "screen_name": screen_name,
            "hashtags": hashtags,
            "snippet": (content[:60] + "…") if len(content) > 60 else content,
        })

    return records


# ─── Neo4j Write ─────────────────────────────────────────────────────────────────
MERGE_QUERY = """
UNWIND $rows AS row
  MERGE (u:User {screen_name: row.screen_name})
  MERGE (t:Tweet {tweet_id: row.tweet_id})
    ON CREATE SET t.content = row.content, t.snippet = row.snippet
  MERGE (u)-[:AUTHORED]->(t)
  WITH t, row
  UNWIND row.hashtags AS tag
    MERGE (h:Hashtag {name: tag})
    MERGE (t)-[:HAS_TAG]->(h)
"""


def push_to_neo4j(records: list[dict]):
    drv = get_driver()
    with drv.session() as s:
        s.run(MERGE_QUERY, rows=records)


# ─── Neo4j Read for Visualisation ────────────────────────────────────────────────
FETCH_QUERY = """
MATCH (u:User)-[:AUTHORED]->(t:Tweet)
OPTIONAL MATCH (t)-[:HAS_TAG]->(h:Hashtag)
RETURN
  u.screen_name AS screen_name,
  t.tweet_id    AS tweet_id,
  t.snippet     AS snippet,
  t.content     AS content,
  collect(h.name) AS hashtags
LIMIT $limit
"""


def fetch_graph(limit: int = 500) -> list[dict]:
    drv = get_driver()
    with drv.session() as s:
        result = s.run(FETCH_QUERY, limit=limit)
        return [dict(r) for r in result]


# ─── Cytoscape Elements Builder ──────────────────────────────────────────────────
USER_COLOR = "#4ab8ff"
TWEET_COLOR = "#f0a500"
HASH_COLOR = "#2ecc71"


def build_cytoscape_elements(rows: list[dict]) -> list[dict]:
    nodes, edges = {}, []

    for row in rows:
        sn = row["screen_name"]
        tid = row["tweet_id"]
        snippet = row["snippet"] or tid
        hashtags = row["hashtags"] or []

        # User node
        if sn not in nodes:
            nodes[sn] = {
                "data": {
                    "id": f"user_{sn}",
                    "label": f"@{sn}",
                    "type": "user",
                    "full_text": f"User: @{sn}",
                },
            }

        # Tweet node
        if tid not in nodes:
            nodes[tid] = {
                "data": {
                    "id": f"tweet_{tid}",
                    "label": snippet,
                    "type": "tweet",
                    "tweet_id": tid,
                    "full_text": row.get("content", snippet),
                },
            }

        # AUTHORED edge
        edges.append({
            "data": {
                "id": f"auth_{sn}_{tid}",
                "source": f"user_{sn}",
                "target": f"tweet_{tid}",
                "label": "AUTHORED",
            }
        })

        # Hashtag nodes + HAS_TAG edges
        for tag in hashtags:
            hid = f"hash_{tag}"
            if hid not in nodes:
                nodes[hid] = {
                    "data": {
                        "id": hid,
                        "label": f"#{tag}",
                        "type": "hashtag",
                        "full_text": f"Hashtag: #{tag}",
                    }
                }
            edges.append({
                "data": {
                    "id": f"tag_{tid}_{tag}",
                    "source": f"tweet_{tid}",
                    "target": hid,
                    "label": "HAS_TAG",
                }
            })

    return list(nodes.values()) + edges


# ─── Cytoscape Stylesheet ────────────────────────────────────────────────────────
CYTO_STYLESHEET = [
    # User → circle
    {
        "selector": "node[type='user']",
        "style": {
            "shape": "ellipse",
            "background-color": USER_COLOR,
            "border-color": "#80d4ff",
            "border-width": 2,
            "label": "data(label)",
            "color": "#ffffff",
            "font-size": "10px",
            "text-valign": "center",
            "text-halign": "center",
            "width": 64,
            "height": 64,
            "font-family": "Share Tech Mono, monospace",
        },
    },
    # Tweet → rectangle
    {
        "selector": "node[type='tweet']",
        "style": {
            "shape": "rectangle",
            "background-color": "#1a2a10",
            "border-color": TWEET_COLOR,
            "border-width": 2,
            "label": "data(label)",
            "color": TWEET_COLOR,
            "font-size": "9px",
            "text-valign": "center",
            "text-halign": "center",
            "width": 120,
            "height": 44,
            "text-wrap": "wrap",
            "text-max-width": "110px",
            "font-family": "Share Tech Mono, monospace",
        },
    },
    # Hashtag → diamond
    {
        "selector": "node[type='hashtag']",
        "style": {
            "shape": "diamond",
            "background-color": "#0d2a1a",
            "border-color": HASH_COLOR,
            "border-width": 2,
            "label": "data(label)",
            "color": HASH_COLOR,
            "font-size": "9px",
            "text-valign": "center",
            "text-halign": "center",
            "width": 54,
            "height": 54,
            "font-family": "Share Tech Mono, monospace",
        },
    },
    # Edges
    {
        "selector": "edge",
        "style": {
            "line-color": "#1e3a50",
            "target-arrow-color": "#1e3a50",
            "target-arrow-shape": "triangle",
            "arrow-scale": 1.2,
            "curve-style": "bezier",
            "label": "data(label)",
            "font-size": "7px",
            "color": "#3a6a8a",
            "font-family": "Share Tech Mono, monospace",
            "text-rotation": "autorotate",
        },
    },
    # Selected
    {
        "selector": ":selected",
        "style": {
            "border-color": "#ffffff",
            "border-width": 3,
            "background-color": "#2a4a6a",
        },
    },
]

CYTO_LAYOUT = {
    "name": "cose",
    "animate": True,
    "animationDuration": 800,
    "nodeRepulsion": 8000,
    "idealEdgeLength": 120,
    "gravity": 0.4,
    "numIter": 1000,
}


# ─── Sidebar ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="section-label">⚙ System Status</div>', unsafe_allow_html=True)

    ok, err = test_connection()
    if ok:
        st.markdown('<div class="status-bar"><span class="status-ok">● NEO4J CONNECTED</span></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="status-bar"><span class="status-err">● NEO4J ERROR</span></div>', unsafe_allow_html=True)
        st.error(err)

    st.markdown("---")
    st.markdown('<div class="section-label">🔍 Graph Controls</div>', unsafe_allow_html=True)
    node_limit = st.slider("Max nodes to fetch", 50, 2000, 500, 50)
    filter_user = st.text_input("Filter by @username", placeholder="e.g. elonmusk")

    st.markdown("---")
    st.markdown('<div class="section-label">📋 Node Detail</div>', unsafe_allow_html=True)
    selected_placeholder = st.empty()

    st.markdown("---")
    st.markdown('<div class="section-label">ℹ Legend</div>', unsafe_allow_html=True)
    st.markdown("""
    🔵 **Circle** — User  
    🟧 **Rectangle** — Tweet  
    🟢 **Diamond** — Hashtag
    """)


# ─── Main Area ───────────────────────────────────────────────────────────────────
tab_ingest, tab_graph, tab_raw = st.tabs(["📥  INGEST", "🕸  GRAPH", "🗄  RAW DATA"])

# ── Tab 1: Ingest ────────────────────────────────────────────────────────────────
with tab_ingest:
    st.markdown('<div class="section-label">Upload Zeeschuimer NDJSON</div>', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Drop your .ndjson file here",
        type=["ndjson", "jsonl", "json"],
        help="Zeeschuimer exports Twitter/X data as newline-delimited JSON.",
    )

    if uploaded:
        raw = uploaded.read()
        records = parse_ndjson(raw)

        # Stats
        users = {r["screen_name"] for r in records}
        tags = {t for r in records for t in r["hashtags"]}

        st.markdown(f"""
        <div class="stat-grid">
          <div class="stat-card"><div class="val">{len(records)}</div><div class="lbl">TWEETS PARSED</div></div>
          <div class="stat-card"><div class="val">{len(users)}</div><div class="lbl">UNIQUE USERS</div></div>
          <div class="stat-card"><div class="val">{len(tags)}</div><div class="lbl">HASHTAGS</div></div>
        </div>
        """, unsafe_allow_html=True)

        if records:
            if st.button("⬆ Push to Neo4j AuraDB", use_container_width=True):
                with st.spinner("Writing to graph database…"):
                    try:
                        push_to_neo4j(records)
                        st.success(f"✅ {len(records)} tweets pushed successfully.")
                    except Exception as e:
                        st.error(f"Neo4j write error: {e}")
        else:
            st.warning("No valid records parsed. Check your .ndjson format.")

# ── Tab 2: Graph ─────────────────────────────────────────────────────────────────
with tab_graph:
    col_refresh, col_clear = st.columns([1, 5])
    with col_refresh:
        refresh = st.button("🔄 Refresh Graph")

    if ok:
        with st.spinner("Loading graph from Neo4j…"):
            try:
                rows = fetch_graph(limit=node_limit)

                # Apply username filter
                if filter_user:
                    fn = filter_user.lstrip("@").lower()
                    rows = [r for r in rows if fn in r["screen_name"].lower()]

                elements = build_cytoscape_elements(rows)

                if not elements:
                    st.info("No data found. Ingest a file first.")
                else:
                    # Node count badge
                    node_count = sum(1 for e in elements if "source" not in e["data"])
                    edge_count = len(elements) - node_count
                    st.markdown(
                        f'<div class="status-bar">'
                        f'<span>NODES: <b style="color:#4ab8ff">{node_count}</b></span>'
                        f'<span>EDGES: <b style="color:#f0a500">{edge_count}</b></span>'
                        f'<span>ROWS: <b style="color:#2ecc71">{len(rows)}</b></span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    selected = st_cytoscapejs(
                        elements=elements,
                        stylesheet=CYTO_STYLESHEET,
                        layout=CYTO_LAYOUT,
                        height="620px",
                        key="falcon_graph",
                    )

                    # Show detail in sidebar when node clicked
                    if selected and selected.get("data"):
                        nd = selected["data"]
                        ntype = nd.get("type", "")
                        label = nd.get("label", "")
                        full_text = nd.get("full_text", label)

                        with selected_placeholder.container():
                            st.markdown(f"**Selected:** `{label}`")
                            st.markdown(f'<div class="tweet-card">'
                                        f'<div class="tweet-meta">TYPE: {ntype.upper()}</div>'
                                        f'{full_text}'
                                        f'</div>', unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Graph fetch error: {e}")
    else:
        st.warning("Neo4j is not connected. Check your secrets.")

# ── Tab 3: Raw Data ──────────────────────────────────────────────────────────────
with tab_raw:
    if ok:
        try:
            rows = fetch_graph(limit=node_limit)
            if rows:
                import pandas as pd
                df = pd.DataFrame(rows).drop(columns=["content"], errors="ignore")
                st.dataframe(df, use_container_width=True, height=500)
                st.download_button(
                    "⬇ Download CSV",
                    df.to_csv(index=False).encode(),
                    "falconx_export.csv",
                    "text/csv",
                )
            else:
                st.info("No records in database yet.")
        except Exception as e:
            st.error(str(e))
    else:
        st.warning("Neo4j not connected.")
