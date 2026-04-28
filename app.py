"""
FalconX OSINT Dashboard
Palantir-style link analysis graph for Zeeschuimer .ndjson Twitter/X data.
Stack: Streamlit + Neo4j (AuraDB) + streamlit-agraph
"""

import json
import streamlit as st
from neo4j import GraphDatabase
from streamlit_agraph import agraph, Node, Edge, Config

# ─── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FalconX OSINT Dashboard",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; background-color: #080d14; color: #c8d6e5; }
  .stApp { background-color: #080d14; }
  .falcon-header { display:flex; align-items:center; gap:14px; padding:18px 0 10px 0; border-bottom:1px solid #1a2a3a; margin-bottom:22px; }
  .falcon-header h1 { font-family:'Rajdhani',sans-serif; font-size:2rem; font-weight:700; color:#e8f4fd; margin:0; letter-spacing:2px; }
  .falcon-header .subtitle { font-family:'Share Tech Mono',monospace; font-size:0.72rem; color:#4a90b8; margin-top:2px; letter-spacing:1px; }
  .badge { background:#0f2236; border:1px solid #1e4060; color:#4ab8ff; padding:3px 10px; border-radius:3px; font-size:0.7rem; font-family:'Share Tech Mono',monospace; letter-spacing:1px; }
  .stat-grid { display:flex; gap:14px; margin-bottom:20px; }
  .stat-card { flex:1; background:#0d1b2a; border:1px solid #1a2e42; border-radius:4px; padding:14px 18px; }
  .stat-card .val { font-size:1.8rem; font-weight:700; color:#4ab8ff; font-family:'Share Tech Mono',monospace; }
  .stat-card .lbl { font-size:0.72rem; color:#5a7a9a; letter-spacing:1px; margin-top:2px; }
  .tweet-card { background:#0d1b2a; border-left:3px solid #4ab8ff; padding:16px; border-radius:0 4px 4px 0; margin-top:12px; font-family:'Share Tech Mono',monospace; font-size:0.82rem; line-height:1.6; color:#a8c8e8; }
  .tweet-meta { color:#4a7090; font-size:0.72rem; margin-bottom:8px; }
  .status-bar { background:#0a1622; border:1px solid #1a2e42; padding:8px 14px; border-radius:3px; margin-bottom:14px; font-family:'Share Tech Mono',monospace; font-size:0.72rem; color:#3a7a9a; display:flex; gap:20px; }
  .status-ok { color:#2ecc71; } .status-err { color:#e74c3c; }
  .section-label { font-size:0.65rem; letter-spacing:2px; color:#3a6a8a; text-transform:uppercase; margin-bottom:8px; font-family:'Share Tech Mono',monospace; }
  [data-testid="stSidebar"] { background:#0a1420 !important; border-right:1px solid #1a2a3a; }
  [data-testid="stSidebar"] * { color:#c8d6e5 !important; }
  .stButton > button { background:#0f2236; border:1px solid #1e4060; color:#4ab8ff; font-family:'Rajdhani',sans-serif; font-weight:600; letter-spacing:1px; border-radius:3px; }
  .stButton > button:hover { background:#1a3a54; border-color:#4ab8ff; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="falcon-header">
  <div>
    <h1>🦅 FALCONX</h1>
    <div class="subtitle">OSINT LINK ANALYSIS DASHBOARD &nbsp;|&nbsp; ZEESCHUIMER INGEST</div>
  </div>
  <div style="margin-left:auto">
    <span class="badge">NEO4J AURADB</span>&nbsp;
    <span class="badge">AGRAPH</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ─── Neo4j ───────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_driver():
    return GraphDatabase.driver(
        st.secrets["NEO4J_URI"],
        auth=(st.secrets["NEO4J_USERNAME"], st.secrets["NEO4J_PASSWORD"])
    )

def test_connection():
    try:
        with get_driver().session() as s:
            s.run("RETURN 1")
        return True, None
    except Exception as e:
        return False, str(e)


# ─── Parsing ─────────────────────────────────────────────────────────────────────
def safe_get(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, {})
    return d if d != {} else default

def extract_hashtags(entities):
    if not entities:
        return []
    return list({
        (ht.get("text") or ht.get("tag", "")).lower()
        for ht in entities.get("hashtags", [])
        if ht.get("text") or ht.get("tag")
    })

def parse_ndjson(raw_bytes):
    records = []
    for line in raw_bytes.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        data = obj.get("data", obj)

        tweet_id    = safe_get(data, "legacy", "id_str") or safe_get(data, "id_str", default="")
        content     = (safe_get(data, "note_tweet", "note_tweet_results", "result", "text")
                       or safe_get(data, "legacy", "full_text") or "")
        screen_name = (safe_get(data, "core", "user_results", "result", "core", "screen_name")
                       or safe_get(data, "core", "user_results", "result", "legacy", "screen_name") or "")

        legacy_ht = extract_hashtags(safe_get(data, "legacy", "entities", default={}))
        note_ht   = extract_hashtags(safe_get(data, "note_tweet", "note_tweet_results", "result", "entity_set", default={}))
        hashtags  = list(set(legacy_ht + note_ht))

        if not tweet_id or not screen_name:
            continue

        records.append({
            "tweet_id":    tweet_id,
            "content":     content,
            "screen_name": screen_name,
            "hashtags":    hashtags,
            "snippet":     (content[:60] + "…") if len(content) > 60 else content,
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
  UNWIND CASE WHEN size(row.hashtags) = 0 THEN [null] ELSE row.hashtags END AS tag
    CALL {
      WITH t, tag
      WITH t, tag WHERE tag IS NOT NULL
      MERGE (h:Hashtag {name: tag})
      MERGE (t)-[:HAS_TAG]->(h)
    }
"""

def push_to_neo4j(records):
    with get_driver().session() as s:
        s.run(MERGE_QUERY, rows=records)


# ─── Neo4j Read ──────────────────────────────────────────────────────────────────
FETCH_QUERY = """
MATCH (u:User)-[:AUTHORED]->(t:Tweet)
OPTIONAL MATCH (t)-[:HAS_TAG]->(h:Hashtag)
RETURN u.screen_name AS screen_name,
       t.tweet_id    AS tweet_id,
       t.snippet     AS snippet,
       t.content     AS content,
       collect(h.name) AS hashtags
LIMIT $limit
"""

def fetch_graph(limit=500):
    with get_driver().session() as s:
        return [dict(r) for r in s.run(FETCH_QUERY, limit=limit)]


# ─── Build agraph elements ───────────────────────────────────────────────────────
def build_agraph(rows, filter_user="", show_hashtags=True):
    nodes, edges = {}, []

    for row in rows:
        sn       = row["screen_name"]
        tid      = row["tweet_id"]
        snippet  = row["snippet"] or tid
        content  = row.get("content", snippet)
        hashtags = row["hashtags"] or []

        if filter_user and filter_user.lower() not in sn.lower():
            continue

        uid = f"user_{sn}"
        if uid not in nodes:
            nodes[uid] = Node(
                id=uid,
                label=f"@{sn}",
                title=f"User: @{sn}",
                shape="dot",
                size=22,
                color={"background": "#1a3a5c", "border": "#4ab8ff",
                       "highlight": {"background": "#2a5a8c", "border": "#80d4ff"}},
                font={"color": "#4ab8ff", "size": 11},
            )

        twid = f"tweet_{tid}"
        if twid not in nodes:
            nodes[twid] = Node(
                id=twid,
                label=snippet,
                title=content,
                shape="box",
                size=16,
                color={"background": "#1a2a10", "border": "#f0a500",
                       "highlight": {"background": "#2a3a18", "border": "#ffc040"}},
                font={"color": "#f0a500", "size": 10},
                widthConstraint={"minimum": 100, "maximum": 180},
            )

        edges.append(Edge(
            source=uid, target=twid,
            label="AUTHORED",
            color={"color": "#1e3a50", "highlight": "#4ab8ff"},
            font={"color": "#3a6a8a", "size": 8},
            arrows="to",
        ))

        if show_hashtags:
            for tag in hashtags:
                hid = f"hash_{tag}"
                if hid not in nodes:
                    nodes[hid] = Node(
                        id=hid,
                        label=f"#{tag}",
                        title=f"Hashtag: #{tag}",
                        shape="diamond",
                        size=14,
                        color={"background": "#0d2a1a", "border": "#2ecc71",
                               "highlight": {"background": "#1a3a28", "border": "#60ee90"}},
                        font={"color": "#2ecc71", "size": 10},
                    )
                edges.append(Edge(
                    source=twid, target=hid,
                    label="HAS_TAG",
                    color={"color": "#1a3020", "highlight": "#2ecc71"},
                    font={"color": "#2a6a3a", "size": 8},
                    arrows="to",
                ))

    return list(nodes.values()), edges


# ─── Graph config ────────────────────────────────────────────────────────────────
def make_config():
    return Config(
        width="100%",
        height=620,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#4ab8ff",
        collapsible=False,
        node={"labelProperty": "label"},
        link={"labelProperty": "label", "renderLabel": False},
    )


# ─── Sidebar ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="section-label">⚙ System Status</div>', unsafe_allow_html=True)
    ok, err = test_connection()
    if ok:
        st.markdown('<div class="status-bar"><span class="status-ok">● NEO4J CONNECTED</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-bar"><span class="status-err">● NEO4J ERROR</span></div>', unsafe_allow_html=True)
        st.error(err)

    st.markdown("---")
    st.markdown('<div class="section-label">🔍 Graph Controls</div>', unsafe_allow_html=True)
    node_limit    = st.slider("Max nodes to fetch", 50, 2000, 500, 50)
    filter_user   = st.text_input("Filter by @username", placeholder="e.g. elonmusk")
    show_hashtags = st.checkbox("Show hashtag nodes", value=True)

    st.markdown("---")
    st.markdown('<div class="section-label">📋 Node Detail</div>', unsafe_allow_html=True)
    detail_placeholder = st.empty()

    st.markdown("---")
    st.markdown("""
    <div class="section-label">ℹ Legend</div>
    🔵 <b>Circle</b> — User<br>
    🟧 <b>Rectangle</b> — Tweet<br>
    🟢 <b>Diamond</b> — Hashtag<br><br>
    <i style="font-size:0.75rem">Click a node to see full text</i>
    """, unsafe_allow_html=True)


# ─── Main tabs ───────────────────────────────────────────────────────────────────
tab_ingest, tab_graph, tab_raw = st.tabs(["📥  INGEST", "🕸  GRAPH", "🗄  RAW DATA"])

# ── Ingest ───────────────────────────────────────────────────────────────────────
with tab_ingest:
    st.markdown('<div class="section-label">Upload Zeeschuimer NDJSON</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Drop your .ndjson file here",
        type=["ndjson", "jsonl", "json"],
        help="Zeeschuimer exports Twitter/X data as newline-delimited JSON.",
    )

    if uploaded:
        records = parse_ndjson(uploaded.read())
        users = {r["screen_name"] for r in records}
        tags  = {t for r in records for t in r["hashtags"]}

        st.markdown(f"""
        <div class="stat-grid">
          <div class="stat-card"><div class="val">{len(records)}</div><div class="lbl">TWEETS PARSED</div></div>
          <div class="stat-card"><div class="val">{len(users)}</div><div class="lbl">UNIQUE USERS</div></div>
          <div class="stat-card"><div class="val">{len(tags)}</div><div class="lbl">HASHTAGS</div></div>
        </div>
        """, unsafe_allow_html=True)

        if records and ok:
            if st.button("⬆ Push to Neo4j AuraDB", use_container_width=True):
                with st.spinner("Writing to graph database…"):
                    try:
                        push_to_neo4j(records)
                        st.success(f"✅ {len(records)} tweets pushed successfully.")
                    except Exception as e:
                        st.error(f"Neo4j write error: {e}")
        elif not ok:
            st.warning("Neo4j is not connected — check your secrets.")
        else:
            st.warning("No valid records parsed. Check your .ndjson format.")

# ── Graph ────────────────────────────────────────────────────────────────────────
with tab_graph:
    if not ok:
        st.warning("Neo4j is not connected. Check your secrets.")
    else:
        if st.button("🔄 Refresh Graph"):
            st.cache_data.clear()

        try:
            rows = fetch_graph(limit=node_limit)
            nodes, edges = build_agraph(rows, filter_user=filter_user, show_hashtags=show_hashtags)

            if not nodes:
                st.info("No data found. Ingest a file first, then refresh.")
            else:
                node_count = len(nodes)
                edge_count = len(edges)
                st.markdown(
                    f'<div class="status-bar">'
                    f'<span>NODES: <b style="color:#4ab8ff">{node_count}</b></span>'
                    f'<span>EDGES: <b style="color:#f0a500">{edge_count}</b></span>'
                    f'<span>ROWS: <b style="color:#2ecc71">{len(rows)}</b></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                clicked = agraph(nodes=nodes, edges=edges, config=make_config())

                if clicked:
                    clicked_node = next((n for n in nodes if n.id == clicked), None)
                    if clicked_node:
                        ntype = ("user"    if clicked.startswith("user_") else
                                 "tweet"   if clicked.startswith("tweet_") else "hashtag")
                        with detail_placeholder.container():
                            st.markdown(f"**Selected:** `{clicked_node.label}`")
                            st.markdown(
                                f'<div class="tweet-card">'
                                f'<div class="tweet-meta">TYPE: {ntype.upper()}</div>'
                                f'{clicked_node.title or clicked_node.label}'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

        except Exception as e:
            st.error(f"Graph error: {e}")

# ── Raw Data ─────────────────────────────────────────────────────────────────────
with tab_raw:
    if not ok:
        st.warning("Neo4j not connected.")
    else:
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
