"""
FalconX — Palantir Gotham-style OSINT Investigation Dashboard
Stack: Streamlit + Neo4j AuraDB + PyVis
"""

import json
import math
import streamlit as st
import streamlit.components.v1 as components
from neo4j import GraphDatabase
from pyvis.network import Network
import tempfile, os

# ── Page config ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FalconX // OSINT",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS — Palantir Gotham HUD aesthetic ───────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=Barlow+Condensed:wght@300;400;500;600;700&family=Barlow:wght@300;400;500&display=swap');

/* ── Reset & base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body, [class*="css"], .stApp {
  background: #070b10 !important;
  color: #8fa8c0 !important;
  font-family: 'Barlow', sans-serif !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #0a0f16; }
::-webkit-scrollbar-thumb { background: #1e3448; border-radius: 2px; }

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
section[data-testid="stSidebar"] { display: none !important; }

/* ── HUD shell ── */
.hud-shell {
  display: grid;
  grid-template-rows: 48px 1fr;
  grid-template-columns: 280px 1fr 300px;
  height: 100vh;
  overflow: hidden;
  background:
    linear-gradient(rgba(0,168,255,0.015) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,168,255,0.015) 1px, transparent 1px);
  background-size: 40px 40px;
  background-color: #070b10;
}

/* ── Top bar ── */
.top-bar {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 0;
  background: #080d14;
  border-bottom: 1px solid #0d2035;
  padding: 0 20px;
  position: relative;
  z-index: 100;
}
.top-bar::after {
  content: '';
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, #00a8ff44, #00a8ff, #00a8ff44, transparent);
}
.logo-block {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-right: 24px;
  border-right: 1px solid #0d2035;
  margin-right: 24px;
}
.logo-icon {
  width: 26px; height: 26px;
  background: linear-gradient(135deg, #00a8ff, #0066cc);
  clip-path: polygon(50% 0%, 100% 38%, 82% 100%, 18% 100%, 0% 38%);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px;
}
.logo-text {
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 4px;
  color: #e0f0ff;
  text-transform: uppercase;
}
.logo-sub {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  color: #00a8ff88;
  letter-spacing: 2px;
  margin-top: 1px;
}
.top-stat {
  display: flex;
  flex-direction: column;
  padding: 0 20px;
  border-right: 1px solid #0d2035;
}
.top-stat-val {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 16px;
  font-weight: 600;
  color: #00a8ff;
  line-height: 1;
}
.top-stat-lbl {
  font-size: 9px;
  color: #3a6080;
  letter-spacing: 2px;
  text-transform: uppercase;
  margin-top: 2px;
}
.top-status {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  color: #3a6080;
  letter-spacing: 1px;
}
.dot-live { width: 6px; height: 6px; border-radius: 50%; background: #00e676; animation: blink 1.4s infinite; }
.dot-err  { width: 6px; height: 6px; border-radius: 50%; background: #ff3d3d; }
@keyframes blink { 0%,100% { opacity:1; } 50% { opacity:.3; } }
.classification {
  margin-left: 24px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  letter-spacing: 3px;
  color: #ff6b00;
  border: 1px solid #ff6b0044;
  padding: 2px 8px;
  border-radius: 2px;
  background: #ff6b0008;
}

/* ── Left panel ── */
.left-panel {
  grid-row: 2;
  background: #080d14;
  border-right: 1px solid #0d2035;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.panel-section {
  border-bottom: 1px solid #0a1a28;
  padding: 14px 16px;
}
.panel-title {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  letter-spacing: 3px;
  color: #00a8ff66;
  text-transform: uppercase;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.panel-title::before {
  content: '';
  width: 12px; height: 1px;
  background: #00a8ff44;
}

/* ── Filter controls ── */
.filter-row { margin-bottom: 10px; }
.filter-label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  color: #3a6080;
  letter-spacing: 1px;
  margin-bottom: 5px;
  text-transform: uppercase;
}

/* ── Legend ── */
.legend-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  border-bottom: 1px solid #0a1826;
  font-size: 11px;
  color: #6a90a8;
}
.legend-item:last-child { border-bottom: none; }
.l-icon {
  width: 28px; height: 20px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.l-circle { width: 16px; height: 16px; border-radius: 50%; border: 2px solid #00a8ff; background: #00a8ff18; }
.l-rect   { width: 22px; height: 12px; border: 2px solid #ff9500; background: #ff950018; border-radius: 2px; }
.l-diamond {
  width: 14px; height: 14px;
  border: 2px solid #00e676;
  background: #00e67618;
  transform: rotate(45deg);
}
.legend-count {
  margin-left: auto;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  color: #1e4060;
}

/* ── Metric cards ── */
.metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.metric-card {
  background: #0a1420;
  border: 1px solid #0d2035;
  border-radius: 3px;
  padding: 10px 12px;
  position: relative;
  overflow: hidden;
}
.metric-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, #00a8ff44, transparent);
}
.metric-val {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 20px;
  font-weight: 600;
  color: #00a8ff;
  line-height: 1;
}
.metric-lbl {
  font-size: 9px;
  color: #2a5070;
  letter-spacing: 2px;
  text-transform: uppercase;
  margin-top: 4px;
}

/* ── Upload zone ── */
.upload-hint {
  border: 1px dashed #0d2035;
  background: #0a1420;
  border-radius: 4px;
  padding: 16px;
  text-align: center;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  color: #2a5070;
  letter-spacing: 1px;
}

/* ── Center graph area ── */
.graph-area {
  grid-row: 2;
  position: relative;
  overflow: hidden;
  background: #070b10;
}
.graph-overlay-tl {
  position: absolute; top: 12px; left: 12px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  color: #1e4060;
  letter-spacing: 1px;
  z-index: 10;
  pointer-events: none;
}
.graph-overlay-br {
  position: absolute; bottom: 12px; right: 12px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  color: #1e4060;
  letter-spacing: 1px;
  z-index: 10;
  pointer-events: none;
  text-align: right;
}
/* Corner brackets */
.graph-area::before, .graph-area::after {
  content: ''; position: absolute; width: 20px; height: 20px; z-index: 5; pointer-events: none;
}
.graph-area::before { top: 8px; left: 8px; border-top: 1px solid #00a8ff44; border-left: 1px solid #00a8ff44; }
.graph-area::after  { bottom: 8px; right: 8px; border-bottom: 1px solid #00a8ff44; border-right: 1px solid #00a8ff44; }

/* ── Right panel — entity detail ── */
.right-panel {
  grid-row: 2;
  background: #080d14;
  border-left: 1px solid #0d2035;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.entity-card {
  background: #0a1520;
  border: 1px solid #0d2035;
  border-radius: 3px;
  margin: 12px;
  overflow: hidden;
}
.entity-card-header {
  background: #0d1e30;
  padding: 10px 14px;
  border-bottom: 1px solid #0d2035;
  display: flex;
  align-items: center;
  gap: 8px;
}
.entity-type-badge {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 8px;
  letter-spacing: 2px;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: 2px;
}
.badge-user    { background: #00a8ff18; border: 1px solid #00a8ff44; color: #00a8ff; }
.badge-tweet   { background: #ff950018; border: 1px solid #ff950044; color: #ff9500; }
.badge-hashtag { background: #00e67618; border: 1px solid #00e67644; color: #00e676; }
.entity-label {
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 14px;
  font-weight: 600;
  color: #c0d8f0;
  margin-left: 4px;
}
.entity-body { padding: 14px; }
.entity-field { margin-bottom: 12px; }
.entity-field-key {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 8px;
  color: #2a5070;
  letter-spacing: 2px;
  text-transform: uppercase;
  margin-bottom: 4px;
}
.entity-field-val {
  font-size: 12px;
  color: #8fa8c0;
  line-height: 1.5;
  word-break: break-word;
}
.entity-field-val.mono {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
}

/* ── Empty state ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 8px;
  color: #1a3a50;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  letter-spacing: 2px;
  text-align: center;
  padding: 24px;
}
.empty-icon {
  font-size: 28px;
  margin-bottom: 8px;
  opacity: 0.3;
}

/* ── Graph tabs inside graph area ── */
.graph-tab-bar {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #0d2035;
  background: #080d14;
}
.graph-tab {
  padding: 8px 20px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  letter-spacing: 2px;
  color: #2a5070;
  cursor: pointer;
  border-right: 1px solid #0d2035;
  text-transform: uppercase;
  transition: all .15s;
}
.graph-tab.active {
  color: #00a8ff;
  background: #00a8ff08;
  border-bottom: 1px solid #00a8ff;
}

/* ── Action button ── */
.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: #0a1a2a;
  border: 1px solid #0d2a40;
  border-radius: 3px;
  color: #00a8ff;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  letter-spacing: 1px;
  cursor: pointer;
  width: 100%;
  margin-bottom: 6px;
  transition: all .15s;
}
.action-btn:hover { background: #0d2235; border-color: #00a8ff44; }
.action-btn.danger { color: #ff4444; border-color: #ff444422; }
.action-btn.success { color: #00e676; border-color: #00e67622; }

/* ── Streamlit widget overrides ── */
.stButton > button {
  background: #0a1a2a !important;
  border: 1px solid #0d2a40 !important;
  color: #00a8ff !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 10px !important;
  letter-spacing: 1px !important;
  border-radius: 3px !important;
  padding: 6px 14px !important;
  width: 100%;
  text-transform: uppercase;
}
.stButton > button:hover { background: #0d2235 !important; border-color: #00a8ff44 !important; }
.stTextInput > div > div > input {
  background: #0a1420 !important;
  border: 1px solid #0d2035 !important;
  border-radius: 3px !important;
  color: #8fa8c0 !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 11px !important;
  padding: 6px 10px !important;
}
.stSelectbox > div > div {
  background: #0a1420 !important;
  border: 1px solid #0d2035 !important;
  border-radius: 3px !important;
  color: #8fa8c0 !important;
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 11px !important;
}
.stSlider > div { padding: 0 !important; }
.stCheckbox > label { color: #6a90a8 !important; font-size: 11px !important; }
.stFileUploader { background: transparent !important; }
.stFileUploader > div { background: #0a1420 !important; border: 1px dashed #0d2035 !important; border-radius: 3px !important; }
.stFileUploader label { color: #2a5070 !important; font-family: 'IBM Plex Mono', monospace !important; font-size: 10px !important; }
.stAlert { background: #0a1420 !important; border: 1px solid #0d2035 !important; border-radius: 3px !important; }
.stSuccess { border-left: 2px solid #00e676 !important; }
.stError   { border-left: 2px solid #ff4444 !important; }
.stWarning { border-left: 2px solid #ff9500 !important; }
div[data-testid="stVerticalBlock"] > div { gap: 6px !important; }
.stMarkdown p { font-size: 12px; color: #6a90a8; }
</style>
""", unsafe_allow_html=True)


# ── Neo4j ─────────────────────────────────────────────────────────────────────────
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


# ── Parsing ───────────────────────────────────────────────────────────────────────
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
        legacy_ht   = extract_hashtags(safe_get(data, "legacy", "entities", default={}))
        note_ht     = extract_hashtags(safe_get(data, "note_tweet", "note_tweet_results", "result", "entity_set", default={}))
        hashtags    = list(set(legacy_ht + note_ht))
        if not tweet_id or not screen_name:
            continue
        records.append({
            "tweet_id": tweet_id, "content": content,
            "screen_name": screen_name, "hashtags": hashtags,
            "snippet": (content[:72] + "…") if len(content) > 72 else content,
        })
    return records


# ── Neo4j write ───────────────────────────────────────────────────────────────────
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


# ── Neo4j read ────────────────────────────────────────────────────────────────────
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

@st.cache_data(ttl=30, show_spinner=False)
def fetch_graph(limit=300):
    with get_driver().session() as s:
        return [dict(r) for r in s.run(FETCH_QUERY, limit=limit)]


# ── PyVis graph builder ───────────────────────────────────────────────────────────
def build_pyvis(rows, show_hashtags=True, filter_user="", layout_mode="force"):
    net = Network(
        height="100%",
        width="100%",
        bgcolor="#070b10",
        font_color="#8fa8c0",
        directed=True,
    )

    # Physics presets
    if layout_mode == "hierarchical":
        net.set_options("""
        {
          "layout": { "hierarchical": {
            "enabled": true,
            "direction": "UD",
            "sortMethod": "directed",
            "levelSeparation": 120,
            "nodeSpacing": 160,
            "treeSpacing": 200
          }},
          "physics": { "enabled": false },
          "edges": { "smooth": { "type": "cubicBezier", "forceDirection": "vertical" } }
        }
        """)
    else:
        net.set_options("""
        {
          "physics": {
            "enabled": true,
            "stabilization": { "iterations": 200, "fit": true },
            "barnesHut": {
              "gravitationalConstant": -8000,
              "centralGravity": 0.3,
              "springLength": 160,
              "springConstant": 0.04,
              "damping": 0.2,
              "avoidOverlap": 0.8
            }
          },
          "edges": {
            "smooth": { "type": "dynamic" },
            "arrows": { "to": { "enabled": true, "scaleFactor": 0.6 } },
            "color": { "color": "#0d2a40", "highlight": "#00a8ff", "hover": "#00a8ff66" },
            "width": 1,
            "selectionWidth": 2,
            "hoverWidth": 1.5
          },
          "nodes": {
            "borderWidth": 1,
            "borderWidthSelected": 2,
            "shadow": { "enabled": true, "color": "rgba(0,168,255,0.15)", "size": 8, "x": 0, "y": 0 }
          },
          "interaction": {
            "hover": true,
            "tooltipDelay": 100,
            "navigationButtons": false,
            "keyboard": { "enabled": true }
          }
        }
        """)

    seen_nodes = set()
    seen_edges = set()

    for row in rows:
        sn      = row["screen_name"]
        tid     = row["tweet_id"]
        snippet = row["snippet"] or tid
        content = row.get("content", snippet)
        tags    = row["hashtags"] or []

        if filter_user and filter_user.lower() not in sn.lower():
            continue

        uid = f"user_{sn}"
        if uid not in seen_nodes:
            seen_nodes.add(uid)
            net.add_node(
                uid,
                label=f"@{sn}",
                title=f"<div style='font-family:monospace;font-size:11px;color:#c0d8f0;padding:6px'>"
                      f"<b style='color:#00a8ff'>USER</b><br>@{sn}</div>",
                shape="dot",
                size=18,
                color={"background": "#0d2235", "border": "#00a8ff",
                       "highlight": {"background": "#0d2a40", "border": "#60c8ff"},
                       "hover":     {"background": "#0d2a40", "border": "#60c8ff"}},
                font={"color": "#00a8ff", "size": 12, "face": "IBM Plex Mono"},
                level=0,
            )

        twid = f"tweet_{tid}"
        if twid not in seen_nodes:
            seen_nodes.add(twid)
            # Wrap label at ~28 chars
            words = snippet.split()
            lines, cur = [], ""
            for w in words:
                if len(cur) + len(w) + 1 > 28 and cur:
                    lines.append(cur)
                    cur = w
                else:
                    cur = (cur + " " + w).strip()
            if cur:
                lines.append(cur)
            wrapped = "\n".join(lines[:3])

            net.add_node(
                twid,
                label=wrapped,
                title=f"<div style='font-family:monospace;font-size:11px;color:#c0d8f0;padding:6px;max-width:260px'>"
                      f"<b style='color:#ff9500'>TWEET</b><br><span style='color:#8fa8c0'>{content[:300]}</span></div>",
                shape="box",
                size=14,
                color={"background": "#150e00", "border": "#ff9500",
                       "highlight": {"background": "#1e1400", "border": "#ffb840"},
                       "hover":     {"background": "#1e1400", "border": "#ffb840"}},
                font={"color": "#ff9500", "size": 9, "face": "IBM Plex Mono"},
                margin=6,
                level=1,
                widthConstraint={"minimum": 90, "maximum": 160},
            )

        eid = f"{uid}__{twid}"
        if eid not in seen_edges:
            seen_edges.add(eid)
            net.add_edge(uid, twid,
                color={"color": "#00a8ff22", "highlight": "#00a8ff"},
                width=1, title="AUTHORED", label="",
                arrows={"to": {"enabled": True, "scaleFactor": 0.5}})

        if show_hashtags:
            for tag in tags:
                hid = f"hash_{tag}"
                if hid not in seen_nodes:
                    seen_nodes.add(hid)
                    net.add_node(
                        hid,
                        label=f"#{tag}",
                        title=f"<div style='font-family:monospace;font-size:11px;padding:6px'>"
                              f"<b style='color:#00e676'>HASHTAG</b><br>#{tag}</div>",
                        shape="diamond",
                        size=12,
                        color={"background": "#001a08", "border": "#00e676",
                               "highlight": {"background": "#002a10", "border": "#60f0a0"},
                               "hover":     {"background": "#002a10", "border": "#60f0a0"}},
                        font={"color": "#00e676", "size": 9, "face": "IBM Plex Mono"},
                        level=2,
                    )
                heid = f"{twid}__{hid}"
                if heid not in seen_edges:
                    seen_edges.add(heid)
                    net.add_edge(twid, hid,
                        color={"color": "#00e67618", "highlight": "#00e676"},
                        width=1, title="HAS_TAG", label="",
                        arrows={"to": {"enabled": True, "scaleFactor": 0.4}},
                        dashes=True)

    return net, len(seen_nodes), len(seen_edges)


def render_graph_html(net):
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        net.save_graph(f.name)
        path = f.name
    with open(path, "r") as f:
        html = f.read()
    os.unlink(path)

    # Inject dark background into the iframe HTML
    html = html.replace(
        "<body>",
        "<body style='background:#070b10;margin:0;padding:0;overflow:hidden;'>"
    ).replace(
        "<html>",
        "<html style='background:#070b10;'>"
    )
    # Remove the vis.js toolbar
    html = html.replace(
        'style="width:100%;height:100%;"',
        'style="width:100%;height:100%;background:#070b10;"'
    )
    return html


# ── Session state ─────────────────────────────────────────────────────────────────
if "selected_node" not in st.session_state:
    st.session_state.selected_node = None
if "graph_rows" not in st.session_state:
    st.session_state.graph_rows = []
if "ingest_stats" not in st.session_state:
    st.session_state.ingest_stats = None
if "active_view" not in st.session_state:
    st.session_state.active_view = "graph"  # graph | ingest | raw
if "layout_mode" not in st.session_state:
    st.session_state.layout_mode = "force"


# ── Connection test ───────────────────────────────────────────────────────────────
neo4j_ok, neo4j_err = test_connection()


# ── Compute stats from fetched rows ───────────────────────────────────────────────
def compute_stats(rows):
    users  = {r["screen_name"] for r in rows}
    tweets = {r["tweet_id"]    for r in rows}
    tags   = {t for r in rows for t in (r["hashtags"] or [])}
    edges  = len(rows) + sum(len(r["hashtags"] or []) for r in rows)
    return len(users), len(tweets), len(tags), edges


# ═══════════════════════════════════════════════════════════════════════════════════
# LAYOUT — 3-column HUD
# ═══════════════════════════════════════════════════════════════════════════════════
left_col, center_col, right_col = st.columns([280, 1, 300], gap="small")

# Quick stats for top bar — fetch only if connected
tb_users = tb_tweets = tb_tags = 0
if neo4j_ok and st.session_state.graph_rows:
    tb_users, tb_tweets, tb_tags, _ = compute_stats(st.session_state.graph_rows)


# ── TOP BAR ───────────────────────────────────────────────────────────────────────
conn_dot  = '<span class="dot-live"></span> AURADB ONLINE' if neo4j_ok else '<span class="dot-err"></span> DB OFFLINE'
st.markdown(f"""
<div class="top-bar">
  <div class="logo-block">
    <div class="logo-icon">🦅</div>
    <div>
      <div class="logo-text">FalconX</div>
      <div class="logo-sub">OSINT // LINK ANALYSIS</div>
    </div>
  </div>
  <div class="top-stat"><div class="top-stat-val">{tb_users}</div><div class="top-stat-lbl">Actors</div></div>
  <div class="top-stat"><div class="top-stat-val">{tb_tweets}</div><div class="top-stat-lbl">Artifacts</div></div>
  <div class="top-stat"><div class="top-stat-val">{tb_tags}</div><div class="top-stat-lbl">Tags</div></div>
  <div class="top-status">{conn_dot}</div>
  <div class="classification">UNCLASSIFIED // OSINT</div>
</div>
""", unsafe_allow_html=True)


# ── LEFT PANEL ────────────────────────────────────────────────────────────────────
with left_col:
    # ── View selector
    st.markdown('<div class="panel-section"><div class="panel-title">View</div>', unsafe_allow_html=True)
    col_v1, col_v2, col_v3 = st.columns(3)
    with col_v1:
        if st.button("GRAPH", key="v_graph"):
            st.session_state.active_view = "graph"
            st.rerun()
    with col_v2:
        if st.button("INGEST", key="v_ingest"):
            st.session_state.active_view = "ingest"
            st.rerun()
    with col_v3:
        if st.button("TABLE", key="v_raw"):
            st.session_state.active_view = "raw"
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Graph controls
    st.markdown('<div class="panel-section"><div class="panel-title">Graph Controls</div>', unsafe_allow_html=True)

    node_limit = st.slider("Node limit", 50, 1000, 300, 50, label_visibility="collapsed")
    st.markdown(f'<div class="filter-label">NODE LIMIT — {node_limit}</div>', unsafe_allow_html=True)

    filter_user = st.text_input("Filter actor", placeholder="@username...", label_visibility="collapsed")
    st.markdown('<div class="filter-label">FILTER BY ACTOR</div>', unsafe_allow_html=True)

    show_hashtags = st.checkbox("Show hashtag nodes", value=True)

    layout_opts = {"Force-directed": "force", "Hierarchical (U→D)": "hierarchical"}
    layout_label = st.selectbox("Layout", list(layout_opts.keys()), label_visibility="collapsed")
    st.markdown('<div class="filter-label">LAYOUT ENGINE</div>', unsafe_allow_html=True)
    st.session_state.layout_mode = layout_opts[layout_label]

    if st.button("⟳  REFRESH GRAPH"):
        fetch_graph.clear()
        if neo4j_ok:
            st.session_state.graph_rows = fetch_graph(limit=node_limit)
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Legend
    n_users = n_tweets = n_tags = 0
    if st.session_state.graph_rows:
        n_users, n_tweets, n_tags, _ = compute_stats(st.session_state.graph_rows)

    st.markdown(f"""
    <div class="panel-section">
      <div class="panel-title">Entity Legend</div>
      <div class="legend-item">
        <div class="l-icon"><div class="l-circle"></div></div>
        <span>Actor / User</span>
        <span class="legend-count">{n_users}</span>
      </div>
      <div class="legend-item">
        <div class="l-icon"><div class="l-rect"></div></div>
        <span>Artifact / Tweet</span>
        <span class="legend-count">{n_tweets}</span>
      </div>
      <div class="legend-item">
        <div class="l-icon"><div class="l-diamond"></div></div>
        <span>Tag / Topic</span>
        <span class="legend-count">{n_tags}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Ingest action (always visible shortcut)
    st.markdown('<div class="panel-section"><div class="panel-title">Data Ingest</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("Drop .ndjson", type=["ndjson", "jsonl", "json"], label_visibility="collapsed")
    if uploaded:
        records = parse_ndjson(uploaded.read())
        u = {r["screen_name"] for r in records}
        t_set = {r["tweet_id"] for r in records}
        tg = {tag for r in records for tag in r["hashtags"]}
        st.session_state.ingest_stats = {"records": records, "users": len(u), "tweets": len(t_set), "tags": len(tg)}
        st.markdown(f"""
        <div class="metric-grid">
          <div class="metric-card"><div class="metric-val">{len(records)}</div><div class="metric-lbl">Parsed</div></div>
          <div class="metric-card"><div class="metric-val">{len(u)}</div><div class="metric-lbl">Actors</div></div>
          <div class="metric-card"><div class="metric-val">{len(t_set)}</div><div class="metric-lbl">Artifacts</div></div>
          <div class="metric-card"><div class="metric-val">{len(tg)}</div><div class="metric-lbl">Tags</div></div>
        </div>
        """, unsafe_allow_html=True)

        if neo4j_ok and records:
            if st.button("⬆  PUSH TO NEO4J"):
                with st.spinner("Writing graph…"):
                    try:
                        push_to_neo4j(records)
                        fetch_graph.clear()
                        st.session_state.graph_rows = fetch_graph(limit=node_limit)
                        st.success(f"✓ {len(records)} artifacts ingested")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    st.markdown('</div>', unsafe_allow_html=True)


# ── CENTER — GRAPH ────────────────────────────────────────────────────────────────
with center_col:
    view = st.session_state.active_view

    # Auto-load on first run
    if neo4j_ok and not st.session_state.graph_rows:
        st.session_state.graph_rows = fetch_graph(limit=node_limit)

    rows = st.session_state.graph_rows

    if view == "graph":
        if not rows:
            st.markdown("""
            <div class="empty-state">
              <div class="empty-icon">◈</div>
              <div>NO GRAPH DATA</div>
              <div style="color:#0d2035;margin-top:4px">Ingest a .ndjson file to begin</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            net, nc, ec = build_pyvis(
                rows,
                show_hashtags=show_hashtags,
                filter_user=filter_user,
                layout_mode=st.session_state.layout_mode
            )
            html = render_graph_html(net)
            # Inject click-to-select JS bridge
            click_js = """
<script>
(function waitForVis() {
  if (typeof network !== 'undefined') {
    network.on('click', function(params) {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const node   = network.body.data.nodes.get(nodeId);
        window.parent.postMessage({ type: 'falconx_select', nodeId: nodeId, label: node.label, title: node.title || '' }, '*');
      }
    });
  } else {
    setTimeout(waitForVis, 200);
  }
})();
</script>
"""
            html = html.replace("</body>", click_js + "</body>")

            # Overlay labels
            st.markdown(f"""
            <div style="font-family:'IBM Plex Mono',monospace;font-size:9px;color:#1a3a50;
                        letter-spacing:1px;padding:4px 0;display:flex;gap:16px">
              <span>NODES <b style="color:#00a8ff">{nc}</b></span>
              <span>EDGES <b style="color:#ff9500">{ec}</b></span>
              <span>ACTORS <b style="color:#00e676">{n_users}</b></span>
              <span style="margin-left:auto">LAYOUT: {st.session_state.layout_mode.upper()}</span>
            </div>
            """, unsafe_allow_html=True)

            components.html(html, height=720, scrolling=False)

    elif view == "ingest":
        st.markdown("""
        <div style="padding:20px">
          <div style="font-family:'IBM Plex Mono',monospace;font-size:9px;color:#00a8ff66;
                      letter-spacing:3px;text-transform:uppercase;margin-bottom:12px">
            Data Ingest // Zeeschuimer NDJSON
          </div>
          <div style="font-size:12px;color:#4a7090;line-height:1.7">
            Use the file uploader in the left panel to load a Zeeschuimer <code style="color:#00a8ff;font-family:monospace">.ndjson</code> export.
            Once parsed, click <b style="color:#00a8ff">PUSH TO NEO4J</b> to write entities and relationships to AuraDB.
            Then switch to Graph view and click <b style="color:#00a8ff">REFRESH GRAPH</b>.
          </div>
        </div>
        """, unsafe_allow_html=True)

    elif view == "raw":
        if rows:
            import pandas as pd
            df = pd.DataFrame(rows)
            # Style the dataframe
            st.markdown("""
            <div style="font-family:'IBM Plex Mono',monospace;font-size:9px;color:#00a8ff66;
                        letter-spacing:3px;text-transform:uppercase;margin-bottom:8px;padding-top:8px">
              Raw Entity Table
            </div>
            """, unsafe_allow_html=True)
            st.dataframe(
                df[["screen_name", "tweet_id", "snippet", "hashtags"]],
                use_container_width=True,
                height=680,
            )
            st.download_button(
                "⬇  EXPORT CSV",
                df.to_csv(index=False).encode(),
                "falconx_export.csv",
                "text/csv",
            )
        else:
            st.markdown('<div class="empty-state"><div class="empty-icon">◫</div><div>NO DATA</div></div>', unsafe_allow_html=True)


# ── RIGHT PANEL — Entity detail ────────────────────────────────────────────────────
with right_col:
    st.markdown('<div class="panel-section"><div class="panel-title">Entity Inspector</div>', unsafe_allow_html=True)

    sel = st.session_state.get("selected_node")

    if not sel:
        st.markdown("""
        <div class="empty-state" style="min-height:200px">
          <div class="empty-icon">◈</div>
          <div>NO ENTITY SELECTED</div>
          <div style="color:#0d2035;margin-top:4px">Click a graph node to inspect</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        nid    = sel.get("id", "")
        label  = sel.get("label", "")
        ntype  = ("user"    if nid.startswith("user_")   else
                  "tweet"   if nid.startswith("tweet_")  else "hashtag")
        badge  = f'<span class="entity-type-badge badge-{ntype}">{ntype.upper()}</span>'

        # Find full data
        full_content = label
        screen_name  = ""
        tweet_id     = ""
        tags         = []

        if ntype == "user":
            screen_name = nid.replace("user_", "")
            user_rows   = [r for r in rows if r["screen_name"] == screen_name]
            full_content = f"@{screen_name}"
            tweet_count  = len(user_rows)
            tag_set      = {t for r in user_rows for t in (r["hashtags"] or [])}

        elif ntype == "tweet":
            tweet_id = nid.replace("tweet_", "")
            t_row    = next((r for r in rows if r["tweet_id"] == tweet_id), None)
            if t_row:
                full_content = t_row.get("content", label)
                screen_name  = t_row.get("screen_name", "")
                tags         = t_row.get("hashtags", [])

        elif ntype == "hashtag":
            tag_name  = nid.replace("hash_", "")
            tag_rows  = [r for r in rows if tag_name in (r["hashtags"] or [])]
            full_content = f"#{tag_name}"

        st.markdown(f"""
        <div class="entity-card">
          <div class="entity-card-header">
            {badge}
            <span class="entity-label">{label.replace(chr(10), ' ')[:40]}</span>
          </div>
          <div class="entity-body">
        """, unsafe_allow_html=True)

        if ntype == "user":
            st.markdown(f"""
            <div class="entity-field">
              <div class="entity-field-key">Screen Name</div>
              <div class="entity-field-val mono">@{screen_name}</div>
            </div>
            <div class="entity-field">
              <div class="entity-field-key">Tweets in Dataset</div>
              <div class="entity-field-val mono">{tweet_count}</div>
            </div>
            <div class="entity-field">
              <div class="entity-field-key">Hashtags Used</div>
              <div class="entity-field-val mono">{len(tag_set)}</div>
            </div>
            <div class="entity-field">
              <div class="entity-field-key">Top Tags</div>
              <div class="entity-field-val">{"  ".join(f"#{t}" for t in list(tag_set)[:8]) or "—"}</div>
            </div>
            """, unsafe_allow_html=True)

        elif ntype == "tweet":
            st.markdown(f"""
            <div class="entity-field">
              <div class="entity-field-key">Tweet ID</div>
              <div class="entity-field-val mono">{tweet_id}</div>
            </div>
            <div class="entity-field">
              <div class="entity-field-key">Author</div>
              <div class="entity-field-val mono">@{screen_name}</div>
            </div>
            <div class="entity-field">
              <div class="entity-field-key">Content</div>
              <div class="entity-field-val">{full_content}</div>
            </div>
            <div class="entity-field">
              <div class="entity-field-key">Hashtags</div>
              <div class="entity-field-val">{"  ".join(f"#{t}" for t in tags) or "—"}</div>
            </div>
            """, unsafe_allow_html=True)

        elif ntype == "hashtag":
            tag_name = nid.replace("hash_", "")
            tag_rows = [r for r in rows if tag_name in (r["hashtags"] or [])]
            authors  = {r["screen_name"] for r in tag_rows}
            st.markdown(f"""
            <div class="entity-field">
              <div class="entity-field-key">Tag</div>
              <div class="entity-field-val mono">#{tag_name}</div>
            </div>
            <div class="entity-field">
              <div class="entity-field-key">Used in Tweets</div>
              <div class="entity-field-val mono">{len(tag_rows)}</div>
            </div>
            <div class="entity-field">
              <div class="entity-field-key">Unique Authors</div>
              <div class="entity-field-val mono">{len(authors)}</div>
            </div>
            <div class="entity-field">
              <div class="entity-field-key">Authors</div>
              <div class="entity-field-val">{"  ".join(f"@{a}" for a in list(authors)[:10])}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Network metrics
    if rows:
        n_u, n_t, n_tg, n_e = compute_stats(rows)
        density = round(n_e / max((n_u + n_t + n_tg) * ((n_u + n_t + n_tg) - 1), 1), 4)
        st.markdown(f"""
        <div class="panel-section">
          <div class="panel-title">Network Metrics</div>
          <div class="metric-grid">
            <div class="metric-card"><div class="metric-val">{n_u}</div><div class="metric-lbl">Actors</div></div>
            <div class="metric-card"><div class="metric-val">{n_t}</div><div class="metric-lbl">Artifacts</div></div>
            <div class="metric-card"><div class="metric-val">{n_tg}</div><div class="metric-lbl">Topics</div></div>
            <div class="metric-card"><div class="metric-val">{n_e}</div><div class="metric-lbl">Relations</div></div>
          </div>
          <div style="margin-top:10px;font-family:'IBM Plex Mono',monospace;font-size:9px;color:#1e4060">
            DENSITY: {density}
          </div>
        </div>
        """, unsafe_allow_html=True)
