"""
FalconX OSINT Investigation Platform
Industry-grade link analysis dashboard — Streamlit + Neo4j + PyVis
"""
import json, os, re, tempfile, html as html_lib
import streamlit as st
import streamlit.components.v1 as components
from neo4j import GraphDatabase

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG — must be first
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FalconX OSINT",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL STYLES  — dark-first, Gotham-grade
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=Syne:wght@400;600;700;800&family=Inter:wght@300;400;500;600&display=swap');

/* ── hard reset ── */
*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp, [data-testid="stAppViewContainer"] {
    background: #080c12 !important;
    color: #c9d8e8 !important;
    font-family: 'Inter', sans-serif !important;
}

/* kill ALL streamlit chrome */
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="collapsedControl"],
[data-testid="stSidebarNav"],
.st-emotion-cache-1dp5vir,
.st-emotion-cache-z5fcl4 { display: none !important; }

/* remove default padding */
[data-testid="stAppViewContainer"] > section { padding: 0 !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
[data-testid="stVerticalBlock"] { gap: 0 !important; }
[data-testid="stHorizontalBlock"] { gap: 0 !important; }

/* ── scrollbar ── */
::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-track { background: #080c12; }
::-webkit-scrollbar-thumb { background: #1e3a54; border-radius: 2px; }

/* ══════════════════════════════════════════════
   TOP BAR
══════════════════════════════════════════════ */
.topbar {
    display: flex;
    align-items: center;
    gap: 0;
    height: 52px;
    background: #0a0f18;
    border-bottom: 1px solid #112236;
    padding: 0 20px;
    position: sticky;
    top: 0;
    z-index: 1000;
}
.topbar-glow {
    position: absolute;
    bottom: -1px; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent 0%, #1a6faa 30%, #2196f3 50%, #1a6faa 70%, transparent 100%);
    opacity: 0.6;
}
.logo {
    display: flex; align-items: center; gap: 10px;
    padding-right: 24px; margin-right: 4px;
    text-decoration: none;
}
.logo-mark {
    width: 32px; height: 32px; flex-shrink: 0;
    background: linear-gradient(135deg, #1565c0 0%, #0d47a1 100%);
    clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
    display: flex; align-items: center; justify-content: center;
    font-size: 15px; color: #fff;
    box-shadow: 0 0 12px rgba(33,150,243,.4);
}
.logo-name {
    font-family: 'Syne', sans-serif;
    font-weight: 800; font-size: 18px;
    letter-spacing: 3px; color: #e8f4ff;
    text-transform: uppercase;
}
.logo-tag {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 8px; color: #2196f3;
    letter-spacing: 2px; opacity: .7;
    margin-top: 1px;
}
.tb-divider {
    width: 1px; height: 28px;
    background: #112236; margin: 0 16px; flex-shrink: 0;
}
.tb-stat {
    display: flex; flex-direction: column;
    padding: 0 16px;
    border-right: 1px solid #0d1e30;
}
.tb-stat:first-of-type { border-left: 1px solid #0d1e30; }
.tb-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 17px; font-weight: 600; color: #2196f3;
    line-height: 1;
}
.tb-lbl {
    font-size: 8px; color: #2a4a68;
    letter-spacing: 2px; text-transform: uppercase; margin-top: 2px;
}
.tb-end { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.status-pill {
    display: flex; align-items: center; gap: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 9px; letter-spacing: 1px;
    padding: 4px 10px;
    border-radius: 2px;
}
.status-ok  { background: #0a1f14; border: 1px solid #1a4a2a; color: #4caf50; }
.status-err { background: #1f0a0a; border: 1px solid #4a1a1a; color: #f44336; }
.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.dot-ok  { background: #4caf50; box-shadow: 0 0 5px #4caf50; animation: blink 2s infinite; }
.dot-err { background: #f44336; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
.classif-badge {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 8px; letter-spacing: 2px;
    color: #e65c00;
    border: 1px solid rgba(230,92,0,.3);
    padding: 3px 9px; border-radius: 2px;
    background: rgba(230,92,0,.06);
    text-transform: uppercase;
}

/* ══════════════════════════════════════════════
   MAIN LAYOUT  — sidebar + content
══════════════════════════════════════════════ */
.layout-wrap {
    display: flex;
    height: calc(100vh - 52px);
    overflow: hidden;
}
.sidebar {
    width: 260px; min-width: 260px;
    background: #0a0f18;
    border-right: 1px solid #112236;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
}
.main {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}
.inspector {
    width: 310px; min-width: 310px;
    background: #0a0f18;
    border-left: 1px solid #112236;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
}

/* ══════════════════════════════════════════════
   SIDEBAR SECTIONS
══════════════════════════════════════════════ */
.sb-section {
    border-bottom: 1px solid #0d1e30;
    padding: 14px 16px;
}
.sb-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 8px; letter-spacing: 3px;
    text-transform: uppercase; color: #1a4a6a;
    margin-bottom: 12px;
    display: flex; align-items: center; gap: 8px;
}
.sb-title::before {
    content: '';
    width: 14px; height: 1px;
    background: linear-gradient(90deg, #2196f3, transparent);
}

/* ── Streamlit widget overrides (dark) ── */
div[data-testid="stSelectbox"] label,
div[data-testid="stSlider"] label,
div[data-testid="stTextInput"] label,
div[data-testid="stCheckbox"] label { display: none !important; }

div[data-testid="stSelectbox"] > div > div {
    background: #0d1e30 !important;
    border: 1px solid #1a3a54 !important;
    border-radius: 3px !important;
    color: #c9d8e8 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 11px !important;
    min-height: 32px !important;
}
div[data-testid="stSelectbox"] svg { fill: #2196f3 !important; }

div[data-testid="stTextInput"] > div > div > input {
    background: #0d1e30 !important;
    border: 1px solid #1a3a54 !important;
    border-radius: 3px !important;
    color: #c9d8e8 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 11px !important;
    padding: 6px 10px !important;
    height: 32px !important;
}
div[data-testid="stTextInput"] > div > div > input:focus {
    border-color: #2196f3 !important;
    box-shadow: 0 0 0 1px #2196f3 !important;
}
div[data-testid="stTextInput"] > div > div > input::placeholder { color: #2a4a68 !important; }

div[data-testid="stSlider"] div[data-baseweb="slider"] > div:last-child {
    background: #1a3a54 !important;
}
div[data-testid="stSlider"] div[role="slider"] {
    background: #2196f3 !important;
    border: 2px solid #2196f3 !important;
    width: 14px !important; height: 14px !important;
}
div[data-testid="stSlider"] [data-testid="stTickBar"] { display: none; }
div[data-testid="stSlider"] p {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 10px !important; color: #2196f3 !important;
}

.stCheckbox > label {
    color: #6a8aa8 !important;
    font-size: 11px !important;
    font-family: 'Inter', sans-serif !important;
}
.stCheckbox > label > span:first-child {
    border-color: #1a3a54 !important;
    background: #0d1e30 !important;
}
.stCheckbox > label > span:first-child[aria-checked="true"] {
    background: #2196f3 !important;
    border-color: #2196f3 !important;
}

/* ── Buttons ── */
.stButton > button {
    background: #0d1e30 !important;
    border: 1px solid #1a3a54 !important;
    border-radius: 3px !important;
    color: #2196f3 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 9px !important;
    letter-spacing: 1px !important;
    text-transform: uppercase !important;
    padding: 6px 14px !important;
    height: 32px !important;
    width: 100% !important;
    transition: all .15s !important;
}
.stButton > button:hover {
    background: #122840 !important;
    border-color: #2196f3 !important;
    box-shadow: 0 0 8px rgba(33,150,243,.2) !important;
}
.danger-btn > button {
    color: #f44336 !important;
    border-color: rgba(244,67,54,.3) !important;
}
.danger-btn > button:hover {
    background: #1a0a0a !important;
    border-color: #f44336 !important;
    box-shadow: 0 0 8px rgba(244,67,54,.2) !important;
}
.primary-btn > button {
    background: #1565c0 !important;
    border-color: #1976d2 !important;
    color: #fff !important;
}
.primary-btn > button:hover {
    background: #1976d2 !important;
    box-shadow: 0 0 12px rgba(33,150,243,.3) !important;
}

/* file uploader */
[data-testid="stFileUploader"] {
    background: transparent !important;
}
[data-testid="stFileUploader"] section {
    background: #0d1e30 !important;
    border: 1px dashed #1a3a54 !important;
    border-radius: 4px !important;
    padding: 12px !important;
}
[data-testid="stFileUploader"] section:hover {
    border-color: #2196f3 !important;
}
[data-testid="stFileUploader"] label {
    color: #2a4a68 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 10px !important;
    letter-spacing: 1px !important;
}
[data-testid="stFileUploader"] button {
    background: #122840 !important;
    border: 1px solid #1a3a54 !important;
    color: #2196f3 !important;
    font-size: 10px !important;
}
[data-testid="stFileUploadDropzone"] span { color: #2a4a68 !important; font-size: 10px !important; }

/* tabs */
[data-testid="stTabs"] [role="tablist"] {
    background: #0a0f18 !important;
    border-bottom: 1px solid #112236 !important;
    padding: 0 16px !important;
    gap: 0 !important;
}
[data-testid="stTabs"] button[role="tab"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 9px !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    color: #2a4a68 !important;
    padding: 10px 18px !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #2196f3 !important;
    border-bottom-color: #2196f3 !important;
    background: rgba(33,150,243,.05) !important;
}
[data-testid="stTabs"] [data-testid="stTabsContent"] {
    background: transparent !important;
    padding: 0 !important;
}

/* dataframe */
[data-testid="stDataFrame"] {
    background: #0a0f18 !important;
}
[data-testid="stDataFrame"] th {
    background: #0d1e30 !important;
    color: #2196f3 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 9px !important;
    letter-spacing: 1px !important;
    border-bottom: 1px solid #1a3a54 !important;
}
[data-testid="stDataFrame"] td {
    background: #080c12 !important;
    color: #8aa8c8 !important;
    font-size: 11px !important;
    border-bottom: 1px solid #0d1e30 !important;
}

/* alerts */
.stAlert {
    background: #0d1e30 !important;
    border-radius: 3px !important;
    border: 1px solid #1a3a54 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 10px !important;
}
[data-testid="stAlertContainer"] [data-baseweb="notification"] {
    background: #0d1e30 !important;
}

/* ══════════════════════════════════════════════
   CUSTOM COMPONENTS
══════════════════════════════════════════════ */
.legend-row {
    display: flex; align-items: center; gap: 10px;
    padding: 7px 0;
    border-bottom: 1px solid #0d1e30;
    font-size: 11px; color: #6a8aa8;
}
.legend-row:last-child { border-bottom: none; }
.l-circle {
    width: 16px; height: 16px; border-radius: 50%;
    border: 2px solid #2196f3; background: rgba(33,150,243,.1);
    flex-shrink: 0;
}
.l-rect {
    width: 22px; height: 13px;
    border: 2px solid #ff9800; background: rgba(255,152,0,.1);
    border-radius: 2px; flex-shrink: 0;
}
.l-diamond {
    width: 13px; height: 13px;
    border: 2px solid #4caf50; background: rgba(76,175,80,.1);
    transform: rotate(45deg); flex-shrink: 0;
}
.l-count {
    margin-left: auto;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px; color: #1a3a54;
}

.metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.metric-card {
    background: #0d1e30;
    border: 1px solid #122840;
    border-radius: 3px;
    padding: 10px 12px;
    position: relative; overflow: hidden;
}
.metric-card::after {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(33,150,243,.4), transparent);
}
.metric-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 20px; font-weight: 600;
    color: #2196f3; line-height: 1;
}
.metric-lbl {
    font-size: 8px; color: #1a3a54;
    letter-spacing: 2px; text-transform: uppercase; margin-top: 4px;
}

.ent-chip {
    display: inline-flex; align-items: center; gap: 4px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 9px; padding: 2px 7px;
    border-radius: 2px; margin: 2px;
    white-space: nowrap;
}
.chip-user { background: rgba(33,150,243,.1); border: 1px solid rgba(33,150,243,.3); color: #2196f3; }
.chip-tweet { background: rgba(255,152,0,.1); border: 1px solid rgba(255,152,0,.3); color: #ff9800; }
.chip-hash  { background: rgba(76,175,80,.1);  border: 1px solid rgba(76,175,80,.3);  color: #4caf50; }

.inspector-header {
    padding: 12px 16px;
    border-bottom: 1px solid #0d1e30;
    background: #0a0f18;
}
.ih-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 8px; letter-spacing: 3px;
    text-transform: uppercase; color: #1a4a6a;
    display: flex; align-items: center; gap: 8px;
}
.ih-title::before {
    content: '';
    width: 14px; height: 1px;
    background: linear-gradient(90deg, #2196f3, transparent);
}

.entity-block {
    background: #0d1e30;
    border: 1px solid #122840;
    border-radius: 3px;
    margin: 12px;
    overflow: hidden;
}
.eb-head {
    padding: 10px 14px;
    border-bottom: 1px solid #0d1e30;
    display: flex; align-items: center; gap: 8px;
    background: #0a1628;
}
.eb-badge {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 7px; letter-spacing: 2px; text-transform: uppercase;
    padding: 2px 8px; border-radius: 2px;
}
.badge-actor   { background: rgba(33,150,243,.12); border: 1px solid rgba(33,150,243,.35); color: #2196f3; }
.badge-artifact{ background: rgba(255,152,0,.12);  border: 1px solid rgba(255,152,0,.35);  color: #ff9800; }
.badge-topic   { background: rgba(76,175,80,.12);  border: 1px solid rgba(76,175,80,.35);  color: #4caf50; }
.eb-name {
    font-family: 'Syne', sans-serif;
    font-size: 13px; font-weight: 600;
    color: #c9d8e8; flex: 1; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
}
.eb-body { padding: 12px 14px; }
.eb-field { margin-bottom: 10px; }
.eb-key {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 7px; letter-spacing: 2px;
    text-transform: uppercase; color: #1a3a54;
    margin-bottom: 3px;
}
.eb-val { font-size: 11px; color: #8aa8c8; line-height: 1.6; word-break: break-word; }
.eb-val.mono { font-family: 'IBM Plex Mono', monospace; font-size: 10px; }

.tweet-preview {
    background: #080c12;
    border: 1px solid #1a3a54;
    border-left: 3px solid #2196f3;
    border-radius: 0 3px 3px 0;
    padding: 12px;
    margin: 10px 14px;
    font-size: 12px;
    color: #a8c4de;
    line-height: 1.7;
    max-height: 200px;
    overflow-y: auto;
}
.tweet-preview .tw-meta {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 9px; color: #2a4a68;
    margin-bottom: 8px;
    display: flex; justify-content: space-between;
}

.density-line {
    display: flex; justify-content: space-between;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 8px; color: #1a3a54;
    padding: 8px 0 0;
    border-top: 1px solid #0d1e30;
    margin-top: 8px;
}
.density-line span:last-child { color: #2196f3; }

.notes-area {
    width: 100%;
    background: #0d1e30;
    border: 1px solid #1a3a54;
    border-radius: 3px;
    color: #8aa8c8;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
    padding: 10px;
    resize: vertical;
    min-height: 100px;
    outline: none;
    line-height: 1.6;
}
.notes-area:focus { border-color: #2196f3; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# NEO4J
# ─────────────────────────────────────────────────────────────────────────────
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
        data        = obj.get("data", obj)
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
            "snippet": (content[:90] + "…") if len(content) > 90 else content,
        })
    return records

MERGE_Q = """
UNWIND $rows AS row
  MERGE (u:User {screen_name: row.screen_name})
  MERGE (t:Tweet {tweet_id: row.tweet_id})
    ON CREATE SET t.content = row.content, t.snippet = row.snippet
  MERGE (u)-[:AUTHORED]->(t)
  WITH t, row
  UNWIND CASE WHEN size(row.hashtags)=0 THEN [null] ELSE row.hashtags END AS tag
    CALL { WITH t,tag WITH t,tag WHERE tag IS NOT NULL
           MERGE (h:Hashtag {name:tag}) MERGE (t)-[:HAS_TAG]->(h) }
"""

def push_to_neo4j(records):
    with get_driver().session() as s:
        s.run(MERGE_Q, rows=records)

def clear_neo4j():
    with get_driver().session() as s:
        s.run("MATCH (n) DETACH DELETE n")

FETCH_Q = """
MATCH (u:User)-[:AUTHORED]->(t:Tweet)
OPTIONAL MATCH (t)-[:HAS_TAG]->(h:Hashtag)
RETURN u.screen_name AS screen_name,
       t.tweet_id    AS tweet_id,
       t.snippet     AS snippet,
       t.content     AS content,
       collect(h.name) AS hashtags
LIMIT $limit
"""

@st.cache_data(ttl=20, show_spinner=False)
def fetch_graph(limit=300):
    with get_driver().session() as s:
        return [dict(r) for r in s.run(FETCH_Q, limit=limit)]


# ─────────────────────────────────────────────────────────────────────────────
# PYVIS GRAPH BUILDER
# ─────────────────────────────────────────────────────────────────────────────
def build_graph_html(rows, show_hashtags=True, filter_user="", layout="force"):
    from pyvis.network import Network

    net = Network(
        height="100%", width="100%",
        bgcolor="#080c12", font_color="#8aa8c8",
        directed=True,
    )

    physics_opts = {
        "physics": {
            "enabled": True,
            "stabilization": {"iterations": 300, "fit": True, "updateInterval": 50},
            "barnesHut": {
                "gravitationalConstant": -10000,
                "centralGravity": 0.2,
                "springLength": 200,
                "springConstant": 0.03,
                "damping": 0.3,
                "avoidOverlap": 1.0
            },
            "minVelocity": 0.75
        },
        "edges": {
            "smooth": {"type": "continuous", "roundness": 0.2},
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}},
            "color": {"color": "#0d2a40", "highlight": "#2196f3", "hover": "#2196f350"},
            "width": 1, "selectionWidth": 2, "hoverWidth": 1.5,
            "font": {"size": 0}
        },
        "nodes": {
            "borderWidth": 1, "borderWidthSelected": 2,
            "shadow": {"enabled": True, "color": "rgba(0,0,0,0.5)", "size": 6, "x": 0, "y": 2}
        },
        "interaction": {
            "hover": True, "tooltipDelay": 60,
            "navigationButtons": False, "keyboard": {"enabled": True},
            "hideEdgesOnDrag": True
        }
    }

    if layout == "hierarchical":
        physics_opts = {
            "layout": {
                "hierarchical": {
                    "enabled": True, "direction": "UD",
                    "sortMethod": "directed",
                    "levelSeparation": 140,
                    "nodeSpacing": 140,
                    "treeSpacing": 160
                }
            },
            "physics": {"enabled": False},
            "edges": {
                "smooth": {"type": "cubicBezier", "forceDirection": "vertical"},
                "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}},
                "color": {"color": "#0d2a40", "highlight": "#2196f3"},
                "width": 1
            },
            "interaction": {
                "hover": True, "tooltipDelay": 60,
                "navigationButtons": False, "keyboard": {"enabled": True}
            }
        }

    net.set_options(json.dumps(physics_opts))

    seen_n, seen_e = set(), set()

    for row in rows:
        sn      = row["screen_name"]
        tid     = row["tweet_id"]
        snippet = (row["snippet"] or tid)[:100]
        content = row.get("content", snippet)
        tags    = row["hashtags"] or []

        if filter_user and filter_user.lower() not in sn.lower():
            continue

        uid = f"u_{sn}"
        if uid not in seen_n:
            seen_n.add(uid)
            net.add_node(
                uid,
                label=f"@{sn}",
                title=(
                    f"<div style='font-family:monospace;background:#0a0f18;color:#c9d8e8;"
                    f"padding:10px;border:1px solid #1a3a54;border-radius:4px;min-width:160px'>"
                    f"<div style='color:#2196f3;font-size:10px;letter-spacing:2px;margin-bottom:6px'>ACTOR</div>"
                    f"<div style='font-size:13px;font-weight:600'>@{sn}</div>"
                    f"</div>"
                ),
                shape="dot", size=20, level=0,
                color={
                    "background": "#0d2a40", "border": "#2196f3",
                    "highlight": {"background": "#122840", "border": "#64b5f6"},
                    "hover":     {"background": "#122840", "border": "#64b5f6"},
                },
                font={"color": "#2196f3", "size": 12, "face": "IBM Plex Mono"},
            )

        # Word-wrap label
        words, lines, cur = snippet.split(), [], ""
        for w in words:
            if len(cur) + len(w) > 24 and cur:
                lines.append(cur); cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur: lines.append(cur)
        label_w = "\n".join(lines[:3])

        twid = f"t_{tid}"
        if twid not in seen_n:
            seen_n.add(twid)
            net.add_node(
                twid,
                label=label_w,
                title=(
                    f"<div style='font-family:monospace;background:#0a0f18;color:#c9d8e8;"
                    f"padding:10px;border:1px solid #1a3a54;border-radius:4px;max-width:280px'>"
                    f"<div style='color:#ff9800;font-size:10px;letter-spacing:2px;margin-bottom:6px'>ARTIFACT</div>"
                    f"<div style='color:#6a8aa8;font-size:9px;margin-bottom:8px'>@{sn}</div>"
                    f"<div style='font-size:11px;line-height:1.6;color:#a8c4de'>{html_lib.escape(content[:300])}</div>"
                    f"{'<div style=\"color:#4caf50;margin-top:8px;font-size:9px\">' + ' '.join(f'#{t}' for t in tags[:8]) + '</div>' if tags else ''}"
                    f"</div>"
                ),
                shape="box", size=14, level=1,
                color={
                    "background": "#130c00", "border": "#ff9800",
                    "highlight": {"background": "#1e1200", "border": "#ffb74d"},
                    "hover":     {"background": "#1e1200", "border": "#ffb74d"},
                },
                font={"color": "#ff9800", "size": 9, "face": "IBM Plex Mono"},
                margin={"top": 6, "right": 8, "bottom": 6, "left": 8},
                widthConstraint={"minimum": 80, "maximum": 160},
            )

        eid = f"{uid}>{twid}"
        if eid not in seen_e:
            seen_e.add(eid)
            net.add_edge(uid, twid,
                title="AUTHORED",
                color={"color": "#0d2a40", "highlight": "#2196f3"},
                width=1,
                arrows={"to": {"enabled": True, "scaleFactor": 0.5}},
            )

        if show_hashtags:
            for tag in tags:
                hid = f"h_{tag}"
                if hid not in seen_n:
                    seen_n.add(hid)
                    net.add_node(
                        hid,
                        label=f"#{tag}",
                        title=(
                            f"<div style='font-family:monospace;background:#0a0f18;color:#c9d8e8;"
                            f"padding:10px;border:1px solid #1a3a54;border-radius:4px'>"
                            f"<div style='color:#4caf50;font-size:10px;letter-spacing:2px;margin-bottom:6px'>TOPIC</div>"
                            f"<div style='font-size:13px'>#{tag}</div>"
                            f"</div>"
                        ),
                        shape="diamond", size=12, level=2,
                        color={
                            "background": "#001a08", "border": "#4caf50",
                            "highlight": {"background": "#002a10", "border": "#81c784"},
                            "hover":     {"background": "#002a10", "border": "#81c784"},
                        },
                        font={"color": "#4caf50", "size": 9, "face": "IBM Plex Mono"},
                    )
                heid = f"{twid}>{hid}"
                if heid not in seen_e:
                    seen_e.add(heid)
                    net.add_edge(twid, hid,
                        title="HAS_TAG",
                        color={"color": "#0a1e12", "highlight": "#4caf50"},
                        width=1, dashes=True,
                        arrows={"to": {"enabled": True, "scaleFactor": 0.4}},
                    )

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        net.save_graph(f.name)
        path = f.name
    with open(path) as f:
        raw = f.read()
    os.unlink(path)

    # Patch for dark bg and no scrollbar
    raw = raw.replace("background-color: white;", "background-color: #080c12;")
    raw = raw.replace(
        "<body>",
        "<body style='margin:0;padding:0;overflow:hidden;background:#080c12'>",
    )
    # Patch the mynetwork div to be full-size absolutely
    raw = re.sub(
        r'#mynetwork\s*\{[^}]*\}',
        '#mynetwork { position:absolute; top:0; left:0; right:0; bottom:0; border:none !important; }',
        raw
    )
    # Inject node-click postMessage
    click_script = """
<script>
(function waitNet() {
  if (typeof network !== 'undefined') {
    network.on('click', function(p) {
      if (p.nodes && p.nodes.length > 0) {
        var id   = p.nodes[0];
        var node = network.body.data.nodes.get(id);
        window.parent.postMessage({
          type: 'falconx_node',
          id: id,
          label: (node && node.label) || '',
          title: (node && node.title) || ''
        }, '*');
      }
    });
  } else { setTimeout(waitNet, 200); }
})();
</script>
"""
    raw = raw.replace("</body>", click_script + "</body>")
    return raw, len(seen_n), len(seen_e)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
for k, v in {
    "rows": [], "limit": 300, "layout": "force",
    "show_tags": True, "filter_user": "",
    "ingest_recs": None, "ingest_stats": None,
    "push_msg": None, "push_ok": None,
    "clear_confirm": False,
    "selected": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────────────────────────────────────
neo4j_ok, neo4j_err = test_connection()
if neo4j_ok and not st.session_state.rows:
    try:
        st.session_state.rows = fetch_graph(limit=st.session_state.limit)
    except Exception:
        pass

rows = st.session_state.rows

# Stats
n_users  = len({r["screen_name"] for r in rows})
n_tweets = len({r["tweet_id"]    for r in rows})
n_tags   = len({t for r in rows for t in (r["hashtags"] or [])})
n_edges  = len(rows) + sum(len(r["hashtags"] or []) for r in rows)
n_nodes  = n_users + n_tweets + (n_tags if st.session_state.show_tags else 0)


# ─────────────────────────────────────────────────────────────────────────────
# TOP BAR
# ─────────────────────────────────────────────────────────────────────────────
conn_html = (
    f'<div class="status-pill status-ok"><div class="dot dot-ok"></div>AURADB ONLINE</div>'
    if neo4j_ok else
    f'<div class="status-pill status-err"><div class="dot dot-err"></div>DB OFFLINE</div>'
)
st.markdown(f"""
<div class="topbar">
  <div class="logo">
    <div class="logo-mark">🦅</div>
    <div>
      <div class="logo-name">FalconX</div>
      <div class="logo-tag">OSINT // LINK ANALYSIS</div>
    </div>
  </div>
  <div class="tb-divider"></div>
  <div class="tb-stat"><div class="tb-val">{n_users}</div><div class="tb-lbl">Actors</div></div>
  <div class="tb-stat"><div class="tb-val">{n_tweets}</div><div class="tb-lbl">Artifacts</div></div>
  <div class="tb-stat"><div class="tb-val">{n_tags}</div><div class="tb-lbl">Topics</div></div>
  <div class="tb-stat"><div class="tb-val">{n_edges}</div><div class="tb-lbl">Relations</div></div>
  <div class="tb-end">
    {conn_html}
    <div class="classif-badge">Unclassified // OSINT</div>
  </div>
  <div class="topbar-glow"></div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# THREE-COLUMN LAYOUT
# ─────────────────────────────────────────────────────────────────────────────
left, center, right = st.columns([260, 9999, 310], gap="small")

# ══════════════════════════════════════════════════════════════════════════════
# LEFT SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with left:
    st.markdown('<div class="sidebar">', unsafe_allow_html=True)

    # ── Graph controls ──────────────────────────────────────────────────────
    st.markdown('<div class="sb-section"><div class="sb-title">Graph Controls</div>', unsafe_allow_html=True)

    st.markdown('<p style="font-family:\'IBM Plex Mono\',monospace;font-size:8px;color:#1a3a54;letter-spacing:2px;text-transform:uppercase;margin:0 0 4px">NODE LIMIT</p>', unsafe_allow_html=True)
    limit = st.slider("limit", 50, 1000, st.session_state.limit, 50, label_visibility="collapsed", key="sl_limit")
    if limit != st.session_state.limit:
        st.session_state.limit = limit

    st.markdown('<p style="font-family:\'IBM Plex Mono\',monospace;font-size:8px;color:#1a3a54;letter-spacing:2px;text-transform:uppercase;margin:8px 0 4px">FILTER ACTOR</p>', unsafe_allow_html=True)
    fu = st.text_input("filter", placeholder="@username…", label_visibility="collapsed",
                       value=st.session_state.filter_user, key="ti_filter")
    st.session_state.filter_user = fu

    st.markdown('<p style="font-family:\'IBM Plex Mono\',monospace;font-size:8px;color:#1a3a54;letter-spacing:2px;text-transform:uppercase;margin:8px 0 4px">LAYOUT ENGINE</p>', unsafe_allow_html=True)
    layout_sel = st.selectbox("layout", ["Force-directed", "Hierarchical (U→D)"],
                              index=0 if st.session_state.layout == "force" else 1,
                              label_visibility="collapsed", key="sel_layout")
    st.session_state.layout = "force" if "Force" in layout_sel else "hierarchical"

    show = st.checkbox("Show hashtag nodes", value=st.session_state.show_tags, key="cb_tags")
    st.session_state.show_tags = show

    if st.button("⟳  Refresh Graph", key="btn_refresh"):
        fetch_graph.clear()
        if neo4j_ok:
            try:
                st.session_state.rows = fetch_graph(limit=st.session_state.limit)
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Entity legend ───────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="sb-section">
      <div class="sb-title">Entity Legend</div>
      <div class="legend-row"><div class="l-circle"></div><span>Actor / User</span><span class="l-count">{n_users}</span></div>
      <div class="legend-row"><div class="l-rect"></div><span>Artifact / Tweet</span><span class="l-count">{n_tweets}</span></div>
      <div class="legend-row"><div class="l-diamond"></div><span>Topic / Hashtag</span><span class="l-count">{n_tags}</span></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Data ingest ─────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section"><div class="sb-title">Data Ingest</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("ndjson", type=["ndjson","jsonl","json"],
                                label_visibility="collapsed", key="uploader")
    if uploaded:
        recs = parse_ndjson(uploaded.read())
        u  = {r["screen_name"] for r in recs}
        ti = {r["tweet_id"]    for r in recs}
        tg = {t for r in recs for t in r["hashtags"]}
        st.session_state.ingest_recs  = recs
        st.session_state.ingest_stats = {"parsed": len(recs), "users": len(u),
                                          "tweets": len(ti), "tags": len(tg)}

    ist = st.session_state.ingest_stats
    if ist:
        st.markdown(f"""
        <div class="metric-grid" style="margin:8px 0">
          <div class="metric-card"><div class="metric-val">{ist["parsed"]}</div><div class="metric-lbl">Parsed</div></div>
          <div class="metric-card"><div class="metric-val">{ist["users"]}</div><div class="metric-lbl">Actors</div></div>
          <div class="metric-card"><div class="metric-val">{ist["tweets"]}</div><div class="metric-lbl">Artifacts</div></div>
          <div class="metric-card"><div class="metric-val">{ist["tags"]}</div><div class="metric-lbl">Topics</div></div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<div class="primary-btn">', unsafe_allow_html=True)
        if st.button("⬆  Push to Neo4j", key="btn_push"):
            if neo4j_ok and st.session_state.ingest_recs:
                with st.spinner("Writing to graph…"):
                    try:
                        push_to_neo4j(st.session_state.ingest_recs)
                        fetch_graph.clear()
                        st.session_state.rows = fetch_graph(limit=st.session_state.limit)
                        st.session_state.push_msg = f"✓ {ist['parsed']} artifacts ingested"
                        st.session_state.push_ok  = True
                        st.rerun()
                    except Exception as e:
                        st.session_state.push_msg = str(e)
                        st.session_state.push_ok  = False
        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.push_msg:
        if st.session_state.push_ok:
            st.success(st.session_state.push_msg)
        else:
            st.error(st.session_state.push_msg)

    st.markdown('</div>', unsafe_allow_html=True)  # close ingest section

    # ── Reset data ─────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section"><div class="sb-title">Database</div>', unsafe_allow_html=True)
    if not st.session_state.clear_confirm:
        st.markdown('<div class="danger-btn">', unsafe_allow_html=True)
        if st.button("✕  Reset All Data", key="btn_clear_1"):
            st.session_state.clear_confirm = True
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.warning("Delete ALL nodes from Neo4j?")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="danger-btn">', unsafe_allow_html=True)
            if st.button("Confirm", key="btn_clear_yes"):
                try:
                    clear_neo4j()
                    fetch_graph.clear()
                    st.session_state.rows         = []
                    st.session_state.clear_confirm = False
                    st.session_state.push_msg     = None
                    st.session_state.ingest_recs  = None
                    st.session_state.ingest_stats = None
                    st.session_state.selected     = None
                    st.success("Database cleared.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            st.markdown('</div>', unsafe_allow_html=True)
        with c2:
            if st.button("Cancel", key="btn_clear_no"):
                st.session_state.clear_confirm = False
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)  # /sidebar


# ══════════════════════════════════════════════════════════════════════════════
# CENTER — TABS
# ══════════════════════════════════════════════════════════════════════════════
with center:
    tab_graph, tab_raw = st.tabs(["🕸  GRAPH", "🗄  RAW TABLE"])

    # ── GRAPH TAB ─────────────────────────────────────────────────────────
    with tab_graph:
        if not rows:
            st.markdown("""
            <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                        height:calc(100vh - 160px);gap:12px;
                        font-family:'IBM Plex Mono',monospace;font-size:10px;
                        color:#1a3a54;letter-spacing:2px;text-align:center">
              <div style="font-size:40px;opacity:.15">◈</div>
              <div>NO GRAPH DATA</div>
              <div style="font-size:9px;color:#0d2035">Ingest a .ndjson file and push to Neo4j, then refresh.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            # stats bar
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:20px;padding:8px 16px;
                        background:#0a0f18;border-bottom:1px solid #0d1e30;
                        font-family:'IBM Plex Mono',monospace;font-size:9px;color:#1a3a54;
                        letter-spacing:1px">
              <span>NODES <b style="color:#2196f3">{n_nodes}</b></span>
              <span>EDGES <b style="color:#ff9800">{n_edges}</b></span>
              <span>ACTORS <b style="color:#4caf50">{n_users}</b></span>
              <span style="margin-left:auto;color:#0d2035;text-transform:uppercase">{st.session_state.layout}</span>
            </div>
            """, unsafe_allow_html=True)

            with st.spinner("Rendering graph…"):
                graph_html, gn, ge = build_graph_html(
                    rows,
                    show_hashtags=st.session_state.show_tags,
                    filter_user=st.session_state.filter_user,
                    layout=st.session_state.layout,
                )

            # Node-click bridge: receive postMessage from pyvis iframe
            bridge = """
<script>
window.addEventListener('message', function(ev) {
    if (!ev.data || ev.data.type !== 'falconx_node') return;
    // Write to a hidden input, then click a hidden button to trigger rerun
    var inp = window.parent.document.getElementById('falconx_node_data');
    if (inp) {
        inp.value = JSON.stringify(ev.data);
        inp.dispatchEvent(new Event('input', {bubbles: true}));
    }
});
</script>
"""
            st.markdown(bridge, unsafe_allow_html=True)
            components.html(graph_html, height=700, scrolling=False)

    # ── RAW TABLE TAB ────────────────────────────────────────────────────
    with tab_raw:
        if rows:
            import pandas as pd
            df = pd.DataFrame(rows)
            df["hashtags"] = df["hashtags"].apply(lambda x: " ".join(f"#{t}" for t in x) if x else "")
            st.dataframe(
                df[["screen_name","tweet_id","snippet","hashtags"]].rename(columns={
                    "screen_name": "Actor",
                    "tweet_id":    "Tweet ID",
                    "snippet":     "Content Snippet",
                    "hashtags":    "Topics",
                }),
                use_container_width=True,
                height=680,
            )
            csv = df.to_csv(index=False).encode()
            st.download_button("⬇  Export CSV", csv, "falconx_export.csv", "text/csv",
                               use_container_width=True)
        else:
            st.markdown("""
            <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                        height:400px;font-family:'IBM Plex Mono',monospace;font-size:10px;
                        color:#1a3a54;letter-spacing:2px;text-align:center">
              <div style="font-size:32px;opacity:.15;margin-bottom:12px">◫</div>
              <div>NO DATA IN DATABASE</div>
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# RIGHT — ENTITY INSPECTOR
# ══════════════════════════════════════════════════════════════════════════════
with right:
    st.markdown('<div class="inspector">', unsafe_allow_html=True)

    # Inspector header
    st.markdown("""
    <div class="inspector-header">
      <div class="ih-title">Entity Inspector</div>
    </div>
    """, unsafe_allow_html=True)

    sel = st.session_state.selected

    if not sel:
        st.markdown("""
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                    padding:40px 20px;gap:10px;
                    font-family:'IBM Plex Mono',monospace;font-size:9px;
                    color:#1a3a54;letter-spacing:2px;text-align:center">
          <div style="font-size:36px;opacity:.1;margin-bottom:4px">◈</div>
          <div>NO ENTITY SELECTED</div>
          <div style="font-size:8px;color:#0d1e30">Click any node in the graph</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        nid   = sel.get("id", "")
        label = sel.get("label", "").replace("\n", " ")
        ntype = ("actor"    if nid.startswith("u_")  else
                 "artifact" if nid.startswith("t_")  else
                 "topic"    if nid.startswith("h_")  else "unknown")
        badge_class = f"badge-{ntype}"

        st.markdown(f"""
        <div class="entity-block">
          <div class="eb-head">
            <span class="eb-badge {badge_class}">{ntype.upper()}</span>
            <span class="eb-name">{html_lib.escape(label[:42])}</span>
          </div>
        """, unsafe_allow_html=True)

        if ntype == "actor":
            sname     = nid[2:]
            act_rows  = [r for r in rows if r["screen_name"] == sname]
            act_tags  = sorted({t for r in act_rows for t in (r["hashtags"] or [])})
            co_actors = sorted({r2["screen_name"] for r in act_rows
                                for r2 in rows
                                if r2["screen_name"] != sname
                                and set(r["hashtags"] or []) & set(r2["hashtags"] or [])})[:8]

            st.markdown(f"""
            <div class="eb-body">
              <div class="eb-field">
                <div class="eb-key">Screen Name</div>
                <div class="eb-val mono">@{sname}</div>
              </div>
              <div class="eb-field">
                <div class="eb-key">Artifacts in Dataset</div>
                <div class="eb-val mono">{len(act_rows)}</div>
              </div>
              <div class="eb-field">
                <div class="eb-key">Unique Topics Used</div>
                <div class="eb-val mono">{len(act_tags)}</div>
              </div>
              <div class="eb-field">
                <div class="eb-key">Top Topics</div>
                <div class="eb-val">
                  {''.join(f'<span class="ent-chip chip-hash">#{t}</span>' for t in act_tags[:10]) or '—'}
                </div>
              </div>
              <div class="eb-field">
                <div class="eb-key">Co-occurring Actors</div>
                <div class="eb-val">
                  {''.join(f'<span class="ent-chip chip-user">@{a}</span>' for a in co_actors) or '—'}
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Recent tweets preview
            if act_rows:
                st.markdown('<div style="padding:0 14px 6px"><div class="eb-key" style="margin-bottom:6px">RECENT ARTIFACTS</div></div>', unsafe_allow_html=True)
                for r in act_rows[:3]:
                    c = html_lib.escape(r.get("content","")[:280])
                    st.markdown(f"""
                    <div class="tweet-preview">
                      <div class="tw-meta">
                        <span>@{sname}</span>
                        <span class="ent-chip chip-tweet" style="margin:0">TWEET {r['tweet_id'][-6:]}</span>
                      </div>
                      {c or "—"}
                    </div>
                    """, unsafe_allow_html=True)

        elif ntype == "artifact":
            tid   = nid[2:]
            t_row = next((r for r in rows if r["tweet_id"] == tid), None)
            if t_row:
                content = html_lib.escape(t_row.get("content",""))
                tags    = t_row.get("hashtags",[])
                sname   = t_row.get("screen_name","")
                st.markdown(f"""
                <div class="eb-body">
                  <div class="eb-field">
                    <div class="eb-key">Tweet ID</div>
                    <div class="eb-val mono" style="word-break:break-all;font-size:9px">{tid}</div>
                  </div>
                  <div class="eb-field">
                    <div class="eb-key">Author</div>
                    <div class="eb-val"><span class="ent-chip chip-user" style="margin:0">@{sname}</span></div>
                  </div>
                  <div class="eb-field">
                    <div class="eb-key">Topics</div>
                    <div class="eb-val">
                      {''.join(f'<span class="ent-chip chip-hash">#{t}</span>' for t in tags) or '—'}
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div class="tweet-preview">
                  <div class="tw-meta">
                    <span>@{sname}</span>
                    <span>FULL CONTENT</span>
                  </div>
                  {content or "—"}
                </div>
                """, unsafe_allow_html=True)

        elif ntype == "topic":
            tag_name = nid[2:]
            tag_rows = [r for r in rows if tag_name in (r["hashtags"] or [])]
            authors  = sorted({r["screen_name"] for r in tag_rows})
            co_tags  = sorted({
                t for r in tag_rows for t in (r["hashtags"] or []) if t != tag_name
            })[:12]
            st.markdown(f"""
            <div class="eb-body">
              <div class="eb-field">
                <div class="eb-key">Hashtag</div>
                <div class="eb-val mono">#{tag_name}</div>
              </div>
              <div class="eb-field">
                <div class="eb-key">Used in Artifacts</div>
                <div class="eb-val mono">{len(tag_rows)}</div>
              </div>
              <div class="eb-field">
                <div class="eb-key">Unique Authors</div>
                <div class="eb-val mono">{len(authors)}</div>
              </div>
              <div class="eb-field">
                <div class="eb-key">Authors</div>
                <div class="eb-val">
                  {''.join(f'<span class="ent-chip chip-user">@{a}</span>' for a in authors[:10]) or '—'}
                </div>
              </div>
              <div class="eb-field">
                <div class="eb-key">Co-occurring Topics</div>
                <div class="eb-val">
                  {''.join(f'<span class="ent-chip chip-hash">#{t}</span>' for t in co_tags) or '—'}
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)  # /entity-block

    # ── Network metrics ─────────────────────────────────────────────────
    density = round(n_edges / max(n_nodes * max(n_nodes - 1, 1), 1), 5)
    st.markdown(f"""
    <div class="sb-section" style="margin:12px">
      <div class="sb-title">Network Metrics</div>
      <div class="metric-grid">
        <div class="metric-card"><div class="metric-val">{n_users}</div><div class="metric-lbl">Actors</div></div>
        <div class="metric-card"><div class="metric-val">{n_tweets}</div><div class="metric-lbl">Artifacts</div></div>
        <div class="metric-card"><div class="metric-val">{n_tags}</div><div class="metric-lbl">Topics</div></div>
        <div class="metric-card"><div class="metric-val">{n_edges}</div><div class="metric-lbl">Relations</div></div>
      </div>
      <div class="density-line"><span>GRAPH DENSITY</span><span>{density}</span></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Investigation Notes ────────────────────────────────────────────
    st.markdown("""
    <div class="sb-section" style="margin:12px;flex:1">
      <div class="sb-title">Investigation Notes</div>
      <textarea class="notes-area" placeholder="Type your analysis notes here…"></textarea>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)  # /inspector


# ─────────────────────────────────────────────────────────────────────────────
# NODE-CLICK RECEIVER
# Streamlit can't natively receive postMessage. We use a URL-param trick:
# the iframe posts to parent, JS in parent writes to a hidden text_input,
# which triggers a widget state change → rerun.
# ─────────────────────────────────────────────────────────────────────────────
node_json = st.text_input("node_data", key="node_data_input",
                           label_visibility="collapsed", value="")

# Hide the input
st.markdown("""
<style>
  [data-testid="stTextInput"]:has(input[aria-label="node_data"]) { display:none!important; }
</style>
<script>
// Give the hidden input an ID for the bridge script
var inputs = window.parent.document.querySelectorAll('[data-testid="stTextInput"] input');
inputs.forEach(function(inp) {
    if (inp.getAttribute('aria-label') === 'node_data') {
        inp.id = 'falconx_node_data';
    }
});
</script>
""", unsafe_allow_html=True)

if node_json:
    try:
        data = json.loads(node_json)
        nid = data.get("id","")
        if nid and (not st.session_state.selected or
                    st.session_state.selected.get("id") != nid):
            st.session_state.selected = data
            # clear the input to allow re-selection of same node
            st.session_state.node_data_input = ""
            st.rerun()
    except Exception:
        pass
