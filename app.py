"""
FalconX — Palantir Gotham-style OSINT Dashboard
"""

import json
import os
import tempfile
import streamlit as st
import streamlit.components.v1 as components
from neo4j import GraphDatabase
from pyvis.network import Network

# ── Page config (minimal — we own 100% of the UI) ───────────────────────────────
st.set_page_config(page_title="FalconX", page_icon="🦅", layout="wide")

# Strip ALL Streamlit chrome so our HTML shell is flush
st.markdown("""
<style>
  #MainMenu, footer, header,
  [data-testid="stToolbar"],
  [data-testid="stDecoration"],
  [data-testid="stStatusWidget"],
  [data-testid="collapsedControl"],
  section[data-testid="stSidebar"] { display:none!important; }
  .block-container { padding:0!important; max-width:100%!important; }
  body, .stApp { background:#f0f2f5!important; overflow:hidden!important; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# BACKEND — Neo4j + Parsing
# ════════════════════════════════════════════════════════════════════════════════

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
            "snippet": (content[:80] + "…") if len(content) > 80 else content,
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

@st.cache_data(ttl=30, show_spinner=False)
def fetch_graph(limit=300):
    with get_driver().session() as s:
        return [dict(r) for r in s.run(FETCH_Q, limit=limit)]


# ════════════════════════════════════════════════════════════════════════════════
# GRAPH BUILDER → returns HTML string
# ════════════════════════════════════════════════════════════════════════════════

def build_graph_html(rows, show_hashtags=True, filter_user="", layout="force", theme="light"):
    if theme == "dark":
        bg         = "#070b10"
        node_bg_u  = "#0d2235";  node_bd_u = "#2196f3"
        node_bg_t  = "#150e00";  node_bd_t = "#ff9500"
        node_bg_h  = "#001a08";  node_bd_h = "#00e676"
        font_u     = "#2196f3";  font_t = "#ff9500";  font_h = "#00e676"
        edge_col   = "#1a3a50"
    else:
        bg         = "#f0f2f5"
        node_bg_u  = "#dbeafe";  node_bd_u = "#1d6fa4"
        node_bg_t  = "#fff7e6";  node_bd_t = "#b45309"
        node_bg_h  = "#dcfce7";  node_bd_h = "#15803d"
        font_u     = "#1d4ed8";  font_t = "#92400e";  font_h = "#166534"
        edge_col   = "#94a3b8"

    net = Network(height="100%", width="100%", bgcolor=bg,
                  font_color="#334155" if theme=="light" else "#8fa8c0",
                  directed=True)

    if layout == "hierarchical":
        net.set_options(json.dumps({
            "layout": {"hierarchical": {
                "enabled": True, "direction": "UD", "sortMethod": "directed",
                "levelSeparation": 130, "nodeSpacing": 150, "treeSpacing": 180
            }},
            "physics": {"enabled": False},
            "edges": {"smooth": {"type": "cubicBezier", "forceDirection": "vertical"}}
        }))
    else:
        net.set_options(json.dumps({
            "physics": {
                "enabled": True,
                "stabilization": {"iterations": 250, "fit": True},
                "barnesHut": {
                    "gravitationalConstant": -9000,
                    "centralGravity": 0.25,
                    "springLength": 180,
                    "springConstant": 0.035,
                    "damping": 0.25,
                    "avoidOverlap": 1.0
                }
            },
            "edges": {
                "smooth": {"type": "dynamic"},
                "arrows": {"to": {"enabled": True, "scaleFactor": 0.6}},
                "color": {"color": edge_col, "highlight": "#2196f3", "hover": "#2196f388"},
                "width": 1, "selectionWidth": 2, "hoverWidth": 1.5
            },
            "nodes": {
                "borderWidth": 1, "borderWidthSelected": 2,
                "shadow": {"enabled": True,
                           "color": "rgba(33,150,243,0.18)" if theme=="dark" else "rgba(0,0,0,0.08)",
                           "size": 8, "x": 0, "y": 2}
            },
            "interaction": {"hover": True, "tooltipDelay": 80, "navigationButtons": False}
        }))

    seen_n, seen_e = set(), set()

    for row in rows:
        sn      = row["screen_name"]
        tid     = row["tweet_id"]
        snippet = row["snippet"] or tid
        content = row.get("content", snippet)
        tags    = row["hashtags"] or []

        if filter_user and filter_user.lower() not in sn.lower():
            continue

        uid = f"user_{sn}"
        if uid not in seen_n:
            seen_n.add(uid)
            net.add_node(uid,
                label=f"@{sn}",
                title=f"<b style='color:{node_bd_u}'>ACTOR</b><br>@{sn}",
                shape="dot", size=20, level=0,
                color={"background": node_bg_u, "border": node_bd_u,
                       "highlight": {"background": node_bg_u, "border": node_bd_u},
                       "hover":     {"background": node_bg_u, "border": node_bd_u}},
                font={"color": font_u, "size": 12, "face": "IBM Plex Mono, monospace", "bold": True})

        # Wrap snippet to ~26 chars/line
        words = snippet.split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) > 26 and cur:
                lines.append(cur); cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur: lines.append(cur)
        label_wrapped = "\n".join(lines[:3])

        twid = f"tweet_{tid}"
        if twid not in seen_n:
            seen_n.add(twid)
            net.add_node(twid,
                label=label_wrapped,
                title=f"<b style='color:{node_bd_t}'>ARTIFACT</b><br>"
                      f"<span style='color:#555'>@{sn}</span><br><br>"
                      f"<span style='font-size:12px'>{content[:280]}</span>",
                shape="box", size=14, level=1,
                color={"background": node_bg_t, "border": node_bd_t,
                       "highlight": {"background": node_bg_t, "border": node_bd_t},
                       "hover":     {"background": node_bg_t, "border": node_bd_t}},
                font={"color": font_t, "size": 9, "face": "IBM Plex Mono, monospace"},
                margin={"top":6,"right":8,"bottom":6,"left":8},
                widthConstraint={"minimum": 90, "maximum": 160})

        eid = f"{uid}>{twid}"
        if eid not in seen_e:
            seen_e.add(eid)
            net.add_edge(uid, twid, title="AUTHORED",
                color={"color": edge_col, "highlight": node_bd_u},
                width=1, arrows={"to": {"enabled": True, "scaleFactor": 0.5}})

        if show_hashtags:
            for tag in tags:
                hid = f"hash_{tag}"
                if hid not in seen_n:
                    seen_n.add(hid)
                    net.add_node(hid,
                        label=f"#{tag}",
                        title=f"<b style='color:{node_bd_h}'>TOPIC</b><br>#{tag}",
                        shape="diamond", size=12, level=2,
                        color={"background": node_bg_h, "border": node_bd_h,
                               "highlight": {"background": node_bg_h, "border": node_bd_h},
                               "hover":     {"background": node_bg_h, "border": node_bd_h}},
                        font={"color": font_h, "size": 9, "face": "IBM Plex Mono, monospace"})
                heid = f"{twid}>{hid}"
                if heid not in seen_e:
                    seen_e.add(heid)
                    net.add_edge(twid, hid, title="HAS_TAG",
                        color={"color": edge_col, "highlight": node_bd_h},
                        width=1, dashes=True,
                        arrows={"to": {"enabled": True, "scaleFactor": 0.4}})

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        net.save_graph(f.name)
        path = f.name
    with open(path) as f:
        raw = f.read()
    os.unlink(path)

    # Patch background & remove vis toolbar scrollbar
    raw = raw.replace("background-color: white;", f"background-color: {bg};")
    raw = raw.replace("<body>", f"<body style='margin:0;padding:0;overflow:hidden;background:{bg}'>")
    raw = raw.replace('<div id="mynetwork"',
                      '<div id="mynetwork" style="position:absolute;top:0;left:0;right:0;bottom:0"')
    return raw, len(seen_n), len(seen_e)


# ════════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ════════════════════════════════════════════════════════════════════════════════
defaults = {
    "rows": [], "theme": "light", "layout": "force",
    "show_tags": True, "filter_user": "", "limit": 300,
    "ingest_records": None, "ingest_stats": None,
    "view": "graph", "push_done": False, "push_err": None,
    "neo4j_ok": False, "neo4j_err": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Check connection once per session
if not st.session_state.neo4j_ok:
    ok, err = test_connection()
    st.session_state.neo4j_ok  = ok
    st.session_state.neo4j_err = err

# Auto-load on startup
if st.session_state.neo4j_ok and not st.session_state.rows:
    try:
        st.session_state.rows = fetch_graph(limit=st.session_state.limit)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════════
# HANDLE FORM POSTS (Streamlit widget state → session_state → rerun)
# ════════════════════════════════════════════════════════════════════════════════

# File upload
uploaded = st.file_uploader("ndjson", type=["ndjson","jsonl","json"],
                             label_visibility="collapsed", key="uploader")
if uploaded:
    records = parse_ndjson(uploaded.read())
    users   = {r["screen_name"] for r in records}
    tids    = {r["tweet_id"]    for r in records}
    tags    = {t for r in records for t in r["hashtags"]}
    st.session_state.ingest_records = records
    st.session_state.ingest_stats   = {
        "parsed": len(records), "users": len(users),
        "tweets": len(tids), "tags": len(tags)
    }

# Push button
if st.button("PUSH", key="push_btn"):
    recs = st.session_state.ingest_records
    if recs and st.session_state.neo4j_ok:
        try:
            push_to_neo4j(recs)
            fetch_graph.clear()
            st.session_state.rows      = fetch_graph(limit=st.session_state.limit)
            st.session_state.push_done = True
            st.session_state.push_err  = None
        except Exception as e:
            st.session_state.push_err  = str(e)
            st.session_state.push_done = False

# Refresh button
if st.button("REFRESH", key="refresh_btn"):
    if st.session_state.neo4j_ok:
        fetch_graph.clear()
        try:
            st.session_state.rows = fetch_graph(limit=st.session_state.limit)
        except Exception:
            pass

# Sliders / inputs — read from query_params trick via hidden inputs below
# (handled via JS postMessage → Streamlit doesn't need to know)

# Hide the raw Streamlit widgets — they're only used as backend triggers
st.markdown("""
<style>
  [data-testid="stFileUploader"],
  [data-testid="stButton"] { position:fixed!important; top:-9999px!important; left:-9999px!important; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# COMPUTE STATS
# ════════════════════════════════════════════════════════════════════════════════
rows   = st.session_state.rows
theme  = st.session_state.theme

n_users  = len({r["screen_name"] for r in rows})
n_tweets = len({r["tweet_id"]    for r in rows})
n_tags   = len({t for r in rows for t in (r["hashtags"] or [])})
n_edges  = len(rows) + sum(len(r["hashtags"] or []) for r in rows)

# Build graph HTML (only if we have data)
graph_html_inner = ""
n_nodes = n_edges_g = 0
if rows:
    graph_html_inner, n_nodes, n_edges_g = build_graph_html(
        rows,
        show_hashtags=st.session_state.show_tags,
        filter_user=st.session_state.filter_user,
        layout=st.session_state.layout,
        theme=theme,
    )
    # Extract just the body content from pyvis HTML
    import re
    body_match = re.search(r'<body[^>]*>(.*)</body>', graph_html_inner, re.DOTALL)
    head_match = re.search(r'<head[^>]*>(.*)</head>', graph_html_inner, re.DOTALL)
    graph_body  = body_match.group(1)  if body_match  else ""
    graph_head  = head_match.group(1)  if head_match  else graph_html_inner


# ════════════════════════════════════════════════════════════════════════════════
# THEME TOKENS
# ════════════════════════════════════════════════════════════════════════════════
if theme == "dark":
    T = {
        "bg":          "#070b10",
        "bg2":         "#0c1420",
        "bg3":         "#0f1e30",
        "border":      "#1a3a50",
        "border2":     "#0d2035",
        "text":        "#8fa8c0",
        "text2":       "#4a7090",
        "text3":       "#1e4060",
        "accent":      "#2196f3",
        "accent2":     "#1565c0",
        "amber":       "#ff9500",
        "green":       "#00e676",
        "red":         "#f44336",
        "topbar":      "#080d14",
        "panel":       "#080d14",
        "card":        "#0c1828",
        "card_border": "#1a3a50",
        "tag_user":    "#0d2235",
        "tag_tweet":   "#150e00",
        "tag_hash":    "#001a08",
        "scrollbar":   "#1e3448",
        "input_bg":    "#0a1420",
        "btn_bg":      "#0d2235",
        "btn_hover":   "#1a3a54",
        "metric_val":  "#2196f3",
        "logo":        "#e0f0ff",
        "graph_bg":    "#070b10",
        "conn_ok":     "#00e676",
        "conn_err":    "#f44336",
        "grid":        "rgba(33,150,243,0.04)",
        "scanline":    "transparent",
    }
else:
    T = {
        "bg":          "#f0f2f5",
        "bg2":         "#ffffff",
        "bg3":         "#e8edf2",
        "border":      "#d0dae6",
        "border2":     "#c8d4e0",
        "text":        "#1e3a52",
        "text2":       "#4a6a88",
        "text3":       "#8aa4bc",
        "accent":      "#1d6fa4",
        "accent2":     "#1558a0",
        "amber":       "#b45309",
        "green":       "#166534",
        "red":         "#b91c1c",
        "topbar":      "#ffffff",
        "panel":       "#ffffff",
        "card":        "#f8fafc",
        "card_border": "#dde5ee",
        "tag_user":    "#dbeafe",
        "tag_tweet":   "#fff7e6",
        "tag_hash":    "#dcfce7",
        "scrollbar":   "#c8d4e0",
        "input_bg":    "#f8fafc",
        "btn_bg":      "#eef3f8",
        "btn_hover":   "#dde8f2",
        "metric_val":  "#1d6fa4",
        "logo":        "#0f2a40",
        "graph_bg":    "#f0f2f5",
        "conn_ok":     "#166534",
        "conn_err":    "#b91c1c",
        "grid":        "rgba(29,111,164,0.05)",
        "scanline":    "transparent",
    }

# Ingest stats JSON for JS
ist = st.session_state.ingest_stats or {}
ist_json = json.dumps(ist)
push_done = st.session_state.push_done
push_err  = st.session_state.push_err or ""

conn_ok  = st.session_state.neo4j_ok
conn_err = st.session_state.neo4j_err or ""

# Table rows for raw view
import html as html_lib
table_rows_html = ""
for r in rows[:500]:
    tags_str = ", ".join(f"#{t}" for t in (r["hashtags"] or []))
    snippet  = html_lib.escape(r["snippet"] or "")
    sn       = html_lib.escape(r["screen_name"])
    tid      = html_lib.escape(r["tweet_id"])
    table_rows_html += f"""
    <tr>
      <td><span class="tag-user">@{sn}</span></td>
      <td class="mono" style="font-size:10px;color:var(--text3)">{tid}</td>
      <td style="max-width:300px;font-size:11px">{snippet}</td>
      <td style="font-size:10px;color:var(--green)">{tags_str}</td>
    </tr>"""


# ════════════════════════════════════════════════════════════════════════════════
# THE FULL HTML SHELL
# ════════════════════════════════════════════════════════════════════════════════
HTML = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=Barlow+Condensed:wght@300;400;500;600;700&family=Barlow:wght@300;400;500&display=swap" rel="stylesheet">
{"" if not rows else (head_match.group(1) if head_match else "")}

<style>
/* ── CSS custom properties ── */
:root {{
  --bg:          {T["bg"]};
  --bg2:         {T["bg2"]};
  --bg3:         {T["bg3"]};
  --border:      {T["border"]};
  --border2:     {T["border2"]};
  --text:        {T["text"]};
  --text2:       {T["text2"]};
  --text3:       {T["text3"]};
  --accent:      {T["accent"]};
  --accent2:     {T["accent2"]};
  --amber:       {T["amber"]};
  --green:       {T["green"]};
  --red:         {T["red"]};
  --topbar:      {T["topbar"]};
  --panel:       {T["panel"]};
  --card:        {T["card"]};
  --card-border: {T["card_border"]};
  --metric-val:  {T["metric_val"]};
  --logo:        {T["logo"]};
  --input-bg:    {T["input_bg"]};
  --btn-bg:      {T["btn_bg"]};
  --btn-hover:   {T["btn_hover"]};
  --scrollbar:   {T["scrollbar"]};
  --green-bg:    {T["tag_hash"]};
  --amber-bg:    {T["tag_tweet"]};
  --blue-bg:     {T["tag_user"]};
}}

/* ── Reset ── */
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{
  width:100%;height:100%;
  background:var(--bg);
  color:var(--text);
  font-family:'Barlow',sans-serif;
  overflow:hidden;
  font-size:13px;
}}
::-webkit-scrollbar{{width:4px;height:4px}}
::-webkit-scrollbar-track{{background:var(--bg)}}
::-webkit-scrollbar-thumb{{background:var(--scrollbar);border-radius:2px}}

/* ── Shell ── */
.shell{{
  display:grid;
  grid-template-rows:48px 1fr;
  grid-template-columns:268px 1fr 288px;
  width:100vw;height:100vh;
  background:
    linear-gradient({T["grid"]} 1px, transparent 1px),
    linear-gradient(90deg, {T["grid"]} 1px, transparent 1px);
  background-size:40px 40px;
  background-color:var(--bg);
}}

/* ── Top bar ── */
.topbar{{
  grid-column:1/-1;
  display:flex;align-items:center;gap:0;
  background:var(--topbar);
  border-bottom:1px solid var(--border);
  padding:0 16px;
  position:relative;z-index:200;
  box-shadow:0 1px 8px rgba(0,0,0,{"0.3" if theme=="dark" else "0.06"});
}}
.topbar-accent{{
  position:absolute;bottom:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,transparent,var(--accent)60%,var(--accent),var(--accent)60%,transparent);
  opacity:0.5;
}}
.logo-block{{
  display:flex;align-items:center;gap:10px;
  padding-right:20px;
  border-right:1px solid var(--border);
  margin-right:20px;
  cursor:default;
}}
.logo-hex{{
  width:28px;height:28px;
  background:var(--accent);
  clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);
  display:flex;align-items:center;justify-content:center;
  color:#fff;font-size:13px;flex-shrink:0;
}}
.logo-text{{
  font-family:'Barlow Condensed',sans-serif;
  font-size:17px;font-weight:700;letter-spacing:4px;
  color:var(--logo);text-transform:uppercase;line-height:1;
}}
.logo-sub{{
  font-family:'IBM Plex Mono',monospace;
  font-size:8px;color:var(--accent);letter-spacing:2px;
  opacity:0.6;margin-top:2px;
}}
.tb-stat{{
  display:flex;flex-direction:column;
  padding:0 16px;border-right:1px solid var(--border2);
}}
.tb-val{{
  font-family:'IBM Plex Mono',monospace;
  font-size:15px;font-weight:600;color:var(--accent);line-height:1;
}}
.tb-lbl{{
  font-size:8px;color:var(--text3);letter-spacing:2px;
  text-transform:uppercase;margin-top:2px;
}}
.tb-right{{
  margin-left:auto;display:flex;align-items:center;gap:12px;
}}
.conn-badge{{
  display:flex;align-items:center;gap:6px;
  font-family:'IBM Plex Mono',monospace;font-size:9px;
  letter-spacing:1px;
}}
.dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;}}
.dot-ok {{background:var(--green);box-shadow:0 0 6px var(--green);animation:pulse 2s infinite;}}
.dot-err{{background:var(--red);}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.classif{{
  font-family:'IBM Plex Mono',monospace;font-size:8px;
  letter-spacing:2px;color:var(--amber);
  border:1px solid color-mix(in srgb, var(--amber) 30%, transparent);
  padding:3px 8px;border-radius:2px;
  background:color-mix(in srgb, var(--amber) 8%, transparent);
}}
.theme-toggle{{
  cursor:pointer;padding:4px 10px;
  background:var(--btn-bg);border:1px solid var(--border);
  border-radius:3px;font-family:'IBM Plex Mono',monospace;
  font-size:9px;color:var(--text2);letter-spacing:1px;
  user-select:none;transition:.15s;
}}
.theme-toggle:hover{{background:var(--btn-hover);color:var(--accent);}}

/* ── Panels ── */
.left-panel,.right-panel{{
  background:var(--panel);
  border-color:var(--border);
  overflow-y:auto;
  display:flex;flex-direction:column;
}}
.left-panel{{
  grid-row:2;
  border-right:1px solid var(--border);
}}
.right-panel{{
  grid-row:2;
  border-left:1px solid var(--border);
}}

.psec{{border-bottom:1px solid var(--border2);padding:12px 14px;}}
.ptitle{{
  font-family:'IBM Plex Mono',monospace;
  font-size:8px;letter-spacing:3px;color:var(--accent);
  text-transform:uppercase;margin-bottom:10px;opacity:0.7;
  display:flex;align-items:center;gap:8px;
}}
.ptitle::before{{content:'';width:10px;height:1px;background:var(--accent);opacity:0.4;}}

/* ── View tabs ── */
.vtabs{{display:flex;gap:0;}}
.vtab{{
  flex:1;padding:7px 0;text-align:center;
  font-family:'IBM Plex Mono',monospace;font-size:8px;
  letter-spacing:2px;text-transform:uppercase;
  cursor:pointer;border-bottom:2px solid transparent;
  color:var(--text3);transition:.15s;
  border-right:1px solid var(--border2);
}}
.vtab:last-child{{border-right:none;}}
.vtab:hover{{color:var(--accent);background:color-mix(in srgb,var(--accent) 5%,transparent);}}
.vtab.active{{color:var(--accent);border-bottom-color:var(--accent);background:color-mix(in srgb,var(--accent) 6%,transparent);}}

/* ── Controls ── */
.ctrl-label{{
  font-family:'IBM Plex Mono',monospace;font-size:8px;
  color:var(--text3);letter-spacing:2px;text-transform:uppercase;
  margin-bottom:4px;display:flex;justify-content:space-between;
}}
.ctrl-label span{{color:var(--accent);}}
.ctrl-row{{margin-bottom:10px;}}
input[type=range]{{
  width:100%;height:3px;-webkit-appearance:none;appearance:none;
  background:var(--border);border-radius:2px;outline:none;cursor:pointer;
}}
input[type=range]::-webkit-slider-thumb{{
  -webkit-appearance:none;width:12px;height:12px;
  background:var(--accent);border-radius:50%;cursor:pointer;
}}
input[type=text]{{
  width:100%;padding:6px 10px;
  background:var(--input-bg);border:1px solid var(--border);
  border-radius:3px;color:var(--text);
  font-family:'IBM Plex Mono',monospace;font-size:10px;outline:none;
  transition:.15s;
}}
input[type=text]:focus{{border-color:var(--accent);}}
select{{
  width:100%;padding:6px 10px;
  background:var(--input-bg);border:1px solid var(--border);
  border-radius:3px;color:var(--text);
  font-family:'IBM Plex Mono',monospace;font-size:10px;outline:none;cursor:pointer;
}}
.chk-row{{display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none;}}
.chk-row input{{accent-color:var(--accent);width:13px;height:13px;cursor:pointer;}}
.chk-row label{{font-size:11px;color:var(--text2);cursor:pointer;}}

/* ── Buttons ── */
.btn{{
  display:flex;align-items:center;justify-content:center;gap:6px;
  padding:7px 12px;background:var(--btn-bg);
  border:1px solid var(--border);border-radius:3px;
  color:var(--accent);font-family:'IBM Plex Mono',monospace;
  font-size:9px;letter-spacing:1px;text-transform:uppercase;
  cursor:pointer;transition:.15s;width:100%;margin-bottom:5px;
}}
.btn:hover{{background:var(--btn-hover);border-color:var(--accent);}}
.btn.primary{{background:var(--accent);color:#fff;border-color:var(--accent2);}}
.btn.primary:hover{{background:var(--accent2);}}
.btn.danger{{color:var(--red);border-color:color-mix(in srgb,var(--red) 30%,transparent);}}

/* ── Legend ── */
.legend-item{{
  display:flex;align-items:center;gap:10px;
  padding:7px 0;border-bottom:1px solid var(--border2);
  font-size:11px;color:var(--text2);
}}
.legend-item:last-child{{border-bottom:none;}}
.l-dot{{width:16px;height:16px;border-radius:50%;border:2px solid var(--accent);background:var(--blue-bg);flex-shrink:0;}}
.l-box{{width:22px;height:13px;border:2px solid var(--amber);background:var(--amber-bg);border-radius:2px;flex-shrink:0;}}
.l-dia{{
  width:14px;height:14px;flex-shrink:0;
  border:2px solid var(--green);background:var(--green-bg);
  transform:rotate(45deg);
}}
.legend-ct{{margin-left:auto;font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--text3);}}

/* ── Metric grid ── */
.mgrid{{display:grid;grid-template-columns:1fr 1fr;gap:6px;}}
.mcard{{
  background:var(--card);border:1px solid var(--card-border);
  border-radius:3px;padding:9px 11px;position:relative;overflow:hidden;
}}
.mcard::before{{
  content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--accent),transparent);opacity:.3;
}}
.mval{{font-family:'IBM Plex Mono',monospace;font-size:18px;font-weight:600;color:var(--metric-val);line-height:1;}}
.mlbl{{font-size:8px;color:var(--text3);letter-spacing:2px;text-transform:uppercase;margin-top:3px;}}

/* ── Upload zone ── */
.upload-zone{{
  border:1px dashed var(--border);background:var(--input-bg);
  border-radius:4px;padding:14px;text-align:center;
  font-family:'IBM Plex Mono',monospace;font-size:9px;
  color:var(--text3);letter-spacing:1px;cursor:pointer;
  transition:.15s;
}}
.upload-zone:hover{{border-color:var(--accent);color:var(--accent);}}
.file-chosen{{
  background:color-mix(in srgb,var(--accent) 8%,transparent);
  border-color:var(--accent);color:var(--accent);
}}

/* ── Alert ── */
.alert{{
  padding:8px 10px;border-radius:3px;
  font-family:'IBM Plex Mono',monospace;font-size:9px;
  letter-spacing:.5px;margin-top:8px;line-height:1.5;
}}
.alert-ok {{background:color-mix(in srgb,var(--green) 10%,transparent);border:1px solid color-mix(in srgb,var(--green) 30%,transparent);color:var(--green);}}
.alert-err{{background:color-mix(in srgb,var(--red)   10%,transparent);border:1px solid color-mix(in srgb,var(--red)   30%,transparent);color:var(--red);}}

/* ── Center graph ── */
.graph-center{{
  grid-row:2;
  position:relative;
  overflow:hidden;
  background:var(--bg);
}}
.graph-topbar{{
  position:absolute;top:0;left:0;right:0;
  height:30px;
  background:var(--bg2);
  border-bottom:1px solid var(--border2);
  display:flex;align-items:center;
  padding:0 12px;gap:16px;
  z-index:50;
  font-family:'IBM Plex Mono',monospace;font-size:9px;color:var(--text3);
  letter-spacing:1px;
}}
.stat-pill{{display:flex;align-items:center;gap:5px;}}
.stat-pill .v{{color:var(--accent);font-weight:600;}}
.graph-frame{{
  position:absolute;top:30px;left:0;right:0;bottom:0;
  overflow:hidden;
}}
.graph-frame iframe{{width:100%;height:100%;border:none;}}
/* Corner brackets */
.corner{{position:absolute;width:16px;height:16px;z-index:60;pointer-events:none;}}
.corner.tl{{top:34px;left:4px;border-top:1px solid var(--accent);border-left:1px solid var(--accent);opacity:.4;}}
.corner.br{{bottom:4px;right:4px;border-bottom:1px solid var(--accent);border-right:1px solid var(--accent);opacity:.4;}}
/* Empty state */
.empty{{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:100%;gap:8px;
  font-family:'IBM Plex Mono',monospace;font-size:10px;
  color:var(--text3);letter-spacing:2px;text-align:center;
}}
.empty-ico{{font-size:32px;opacity:.2;margin-bottom:6px;}}

/* ── Right panel ── */
.entity-card{{
  background:var(--card);border:1px solid var(--card-border);
  border-radius:4px;margin:10px;overflow:hidden;
}}
.ent-header{{
  background:var(--bg3);padding:9px 13px;
  border-bottom:1px solid var(--border2);
  display:flex;align-items:center;gap:8px;
}}
.ent-badge{{
  font-family:'IBM Plex Mono',monospace;font-size:7px;
  letter-spacing:2px;text-transform:uppercase;
  padding:2px 7px;border-radius:2px;
}}
.badge-user   {{background:var(--blue-bg);border:1px solid color-mix(in srgb,var(--accent) 40%,transparent);color:var(--accent);}}
.badge-tweet  {{background:var(--amber-bg);border:1px solid color-mix(in srgb,var(--amber) 40%,transparent);color:var(--amber);}}
.badge-hashtag{{background:var(--green-bg);border:1px solid color-mix(in srgb,var(--green) 40%,transparent);color:var(--green);}}
.ent-name{{
  font-family:'Barlow Condensed',sans-serif;font-size:13px;
  font-weight:600;color:var(--text);
}}
.ent-body{{padding:12px 13px;}}
.ent-field{{margin-bottom:11px;}}
.ent-key{{
  font-family:'IBM Plex Mono',monospace;font-size:7px;
  color:var(--text3);letter-spacing:2px;text-transform:uppercase;margin-bottom:3px;
}}
.ent-val{{font-size:11px;color:var(--text2);line-height:1.5;word-break:break-word;}}
.mono{{font-family:'IBM Plex Mono',monospace!important;}}

/* ── Tags ── */
.tag-user   {{display:inline-block;padding:1px 6px;border-radius:2px;background:var(--blue-bg);color:var(--accent);font-family:'IBM Plex Mono',monospace;font-size:10px;margin:1px;}}
.tag-tweet  {{display:inline-block;padding:1px 6px;border-radius:2px;background:var(--amber-bg);color:var(--amber);font-family:'IBM Plex Mono',monospace;font-size:10px;margin:1px;}}
.tag-hash   {{display:inline-block;padding:1px 6px;border-radius:2px;background:var(--green-bg);color:var(--green);font-family:'IBM Plex Mono',monospace;font-size:10px;margin:1px;}}

/* ── Table ── */
.tbl-wrap{{overflow:auto;max-height:calc(100vh - 100px);padding:10px;}}
table{{width:100%;border-collapse:collapse;font-size:11px;}}
th{{
  font-family:'IBM Plex Mono',monospace;font-size:8px;letter-spacing:2px;
  text-transform:uppercase;color:var(--text3);
  padding:8px 10px;border-bottom:1px solid var(--border);
  text-align:left;background:var(--bg2);position:sticky;top:0;z-index:10;
}}
td{{
  padding:7px 10px;border-bottom:1px solid var(--border2);
  color:var(--text2);vertical-align:top;
}}
tr:hover td{{background:color-mix(in srgb,var(--accent) 4%,transparent);}}

/* ── Density ── */
.density-row{{
  display:flex;justify-content:space-between;align-items:center;
  padding:8px 0 0;
  font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--text3);letter-spacing:1px;
}}
</style>
</head>
<body>
<div class="shell">

<!-- ═══ TOP BAR ═══ -->
<div class="topbar">
  <div class="logo-block">
    <div class="logo-hex">🦅</div>
    <div>
      <div class="logo-text">FalconX</div>
      <div class="logo-sub">OSINT // LINK ANALYSIS</div>
    </div>
  </div>
  <div class="tb-stat"><div class="tb-val">{n_users}</div><div class="tb-lbl">Actors</div></div>
  <div class="tb-stat"><div class="tb-val">{n_tweets}</div><div class="tb-lbl">Artifacts</div></div>
  <div class="tb-stat"><div class="tb-val">{n_tags}</div><div class="tb-lbl">Topics</div></div>
  <div class="tb-stat" style="border-right:none"><div class="tb-val">{n_edges_g}</div><div class="tb-lbl">Relations</div></div>
  <div class="tb-right">
    <div class="conn-badge">
      <div class="dot {"dot-ok" if conn_ok else "dot-err"}"></div>
      <span style="color:{"var(--green)" if conn_ok else "var(--red)"}">
        {"AURADB ONLINE" if conn_ok else "DB OFFLINE"}
      </span>
    </div>
    <div class="classif">UNCLASSIFIED // OSINT</div>
    <div class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">
      {"☀ LIGHT" if theme=="dark" else "◑ DARK"}
    </div>
  </div>
  <div class="topbar-accent"></div>
</div>

<!-- ═══ LEFT PANEL ═══ -->
<div class="left-panel">

  <!-- View tabs -->
  <div class="psec" style="padding:0">
    <div class="vtabs">
      <div class="vtab {"active" if st.session_state.view=="graph" else ""}" onclick="setView('graph')">Graph</div>
      <div class="vtab {"active" if st.session_state.view=="ingest" else ""}" onclick="setView('ingest')">Ingest</div>
      <div class="vtab {"active" if st.session_state.view=="raw" else ""}" onclick="setView('raw')">Table</div>
    </div>
  </div>

  <!-- Graph controls -->
  <div class="psec">
    <div class="ptitle">Graph Controls</div>

    <div class="ctrl-row">
      <div class="ctrl-label">Node Limit <span id="limitVal">{st.session_state.limit}</span></div>
      <input type="range" min="50" max="1000" step="50" value="{st.session_state.limit}"
             oninput="document.getElementById('limitVal').textContent=this.value"
             onchange="sendCtrl('limit', this.value)">
    </div>

    <div class="ctrl-row">
      <div class="ctrl-label">Filter Actor</div>
      <input type="text" placeholder="@username…" value="{st.session_state.filter_user}"
             onchange="sendCtrl('filter', this.value)">
    </div>

    <div class="ctrl-row">
      <div class="ctrl-label">Layout Engine</div>
      <select onchange="sendCtrl('layout', this.value)">
        <option value="force" {"selected" if st.session_state.layout=="force" else ""}>Force-directed</option>
        <option value="hierarchical" {"selected" if st.session_state.layout=="hierarchical" else ""}>Hierarchical (U→D)</option>
      </select>
    </div>

    <div class="ctrl-row">
      <div class="chk-row">
        <input type="checkbox" id="showTags" {"checked" if st.session_state.show_tags else ""}
               onchange="sendCtrl('show_tags', this.checked)">
        <label for="showTags">Show hashtag nodes</label>
      </div>
    </div>

    <button class="btn" onclick="sendCtrl('refresh', '1')">⟳ Refresh Graph</button>
  </div>

  <!-- Legend -->
  <div class="psec">
    <div class="ptitle">Entity Legend</div>
    <div class="legend-item"><div class="l-dot"></div><span>Actor / User</span><span class="legend-ct">{n_users}</span></div>
    <div class="legend-item"><div class="l-box"></div><span>Artifact / Tweet</span><span class="legend-ct">{n_tweets}</span></div>
    <div class="legend-item"><div class="l-dia"></div><span>Topic / Hashtag</span><span class="legend-ct">{n_tags}</span></div>
  </div>

  <!-- Ingest section -->
  <div class="psec" id="ingestPanel">
    <div class="ptitle">Data Ingest</div>
    <div class="upload-zone" id="dropZone" onclick="triggerUpload()">
      {"📁 " + (st.session_state.ingest_stats and str(ist.get("parsed","0")) + " records loaded" or "Drop .ndjson or click to upload")}
    </div>

    {'<div class="mgrid" style="margin-top:8px">'
      + f'<div class="mcard"><div class="mval">{ist.get("parsed",0)}</div><div class="mlbl">Parsed</div></div>'
      + f'<div class="mcard"><div class="mval">{ist.get("users",0)}</div><div class="mlbl">Actors</div></div>'
      + f'<div class="mcard"><div class="mval">{ist.get("tweets",0)}</div><div class="mlbl">Artifacts</div></div>'
      + f'<div class="mcard"><div class="mval">{ist.get("tags",0)}</div><div class="mlbl">Topics</div></div>'
      + '</div>'
      if ist else ""}

    {'<div class="alert alert-ok">✓ ' + str(ist.get("parsed",0)) + ' artifacts pushed to Neo4j</div>' if push_done else ""}
    {'<div class="alert alert-err">✗ ' + push_err + '</div>' if push_err else ""}

    {"" if not ist else '<button class="btn primary" style="margin-top:8px" onclick="triggerPush()">⬆ Push to Neo4j</button>'}
  </div>

</div><!-- /left-panel -->


<!-- ═══ CENTER GRAPH ═══ -->
<div class="graph-center" id="mainView">

  <!-- Graph view -->
  <div id="view-graph" style="position:absolute;inset:0;display:{"block" if st.session_state.view=="graph" else "none"}">
    <div class="graph-topbar">
      <div class="stat-pill">NODES <span class="v">{n_nodes}</span></div>
      <div class="stat-pill">EDGES <span class="v">{n_edges_g}</span></div>
      <div class="stat-pill">ACTORS <span class="v">{n_users}</span></div>
      <span style="margin-left:auto;text-transform:uppercase">{st.session_state.layout}</span>
    </div>
    <div class="graph-frame">
      {"<iframe srcdoc='" + graph_body.replace("'", "&#39;") + "'></iframe>"
       if rows and graph_body else
       '<div class="empty"><div class="empty-ico">◈</div><div>NO GRAPH DATA</div><div style="margin-top:4px;font-size:9px">Ingest a .ndjson file to begin</div></div>'}
    </div>
    <div class="corner tl"></div>
    <div class="corner br"></div>
  </div>

  <!-- Ingest guide view -->
  <div id="view-ingest" style="position:absolute;inset:0;display:{"block" if st.session_state.view=="ingest" else "none"};padding:32px;overflow-y:auto">
    <div style="max-width:560px">
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:22px;font-weight:700;color:var(--text);letter-spacing:2px;margin-bottom:6px">DATA INGEST</div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:8px;color:var(--accent);letter-spacing:3px;margin-bottom:24px">ZEESCHUIMER NDJSON PIPELINE</div>
      <div style="color:var(--text2);line-height:1.8;font-size:12px">
        <p style="margin-bottom:16px">Use the file uploader in the left panel to load a Zeeschuimer <span class="tag-user">.ndjson</span> export from Twitter/X.</p>
        <p style="margin-bottom:16px">Once parsed, click <span class="tag-user">PUSH TO NEO4J</span> to write all entities and relationships to AuraDB.</p>
        <p>Then switch to <span class="tag-user">Graph</span> view and click <span class="tag-user">REFRESH GRAPH</span>.</p>
      </div>
    </div>
  </div>

  <!-- Raw table view -->
  <div id="view-raw" style="position:absolute;inset:0;display:{"block" if st.session_state.view=="raw" else "none"}">
    {"" if not rows else f'''
    <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th>Actor</th><th>Tweet ID</th><th>Snippet</th><th>Tags</th>
      </tr></thead>
      <tbody>{table_rows_html}</tbody>
    </table>
    </div>''' if rows else '<div class="empty"><div class="empty-ico">◫</div><div>NO DATA</div></div>'}
  </div>

</div><!-- /graph-center -->


<!-- ═══ RIGHT PANEL — Entity Inspector ═══ -->
<div class="right-panel">
  <div class="psec">
    <div class="ptitle">Entity Inspector</div>

    <div id="noEntity" style="{"display:none" if False else "display:block"}">
      <div class="empty" style="min-height:160px;padding:0">
        <div class="empty-ico">◈</div>
        <div>NO ENTITY SELECTED</div>
        <div style="font-size:9px;margin-top:3px">Click any graph node</div>
      </div>
    </div>

    <div id="entityCard" style="display:none"></div>
  </div>

  <!-- Network metrics -->
  <div class="psec">
    <div class="ptitle">Network Metrics</div>
    <div class="mgrid">
      <div class="mcard"><div class="mval">{n_users}</div><div class="mlbl">Actors</div></div>
      <div class="mcard"><div class="mval">{n_tweets}</div><div class="mlbl">Artifacts</div></div>
      <div class="mcard"><div class="mval">{n_tags}</div><div class="mlbl">Topics</div></div>
      <div class="mcard"><div class="mval">{n_edges_g}</div><div class="mlbl">Relations</div></div>
    </div>
    <div class="density-row">
      <span>DENSITY</span>
      <span style="color:var(--accent)">{round(n_edges_g / max((n_nodes) * max(n_nodes - 1, 1), 1), 5)}</span>
    </div>
  </div>

  <!-- Investigation notes -->
  <div class="psec" style="flex:1">
    <div class="ptitle">Investigation Notes</div>
    <textarea id="notes" placeholder="Type your analysis notes here…"
      style="width:100%;min-height:140px;background:var(--input-bg);border:1px solid var(--border);
             border-radius:3px;color:var(--text);font-family:'IBM Plex Mono',monospace;
             font-size:10px;padding:9px;resize:vertical;outline:none;line-height:1.6"
    ></textarea>
  </div>
</div><!-- /right-panel -->

</div><!-- /shell -->


<!-- ═══ JAVASCRIPT ═══ -->
<script>
// ── View switcher ──────────────────────────────────────────────────────────────
function setView(v) {{
  ['graph','ingest','raw'].forEach(function(id) {{
    var el = document.getElementById('view-' + id);
    if (el) el.style.display = (id === v) ? 'block' : 'none';
  }});
  document.querySelectorAll('.vtab').forEach(function(t) {{
    t.classList.toggle('active', t.textContent.trim().toLowerCase() === v ||
      (v === 'raw' && t.textContent.trim().toLowerCase() === 'table'));
  }});
  // notify python
  window.parent.postMessage({{type:'falconx', action:'view', value: v}}, '*');
}}

// ── Theme toggle ───────────────────────────────────────────────────────────────
function toggleTheme() {{
  window.parent.postMessage({{type:'falconx', action:'theme',
    value: '{theme}' === 'dark' ? 'light' : 'dark'}}, '*');
}}

// ── Control change → tell Streamlit to rerun ──────────────────────────────────
function sendCtrl(key, val) {{
  window.parent.postMessage({{type:'falconx', action:'ctrl', key:key, value:val}}, '*');
}}

// ── File upload trigger ────────────────────────────────────────────────────────
function triggerUpload() {{
  window.parent.postMessage({{type:'falconx', action:'upload'}}, '*');
}}

// ── Push trigger ───────────────────────────────────────────────────────────────
function triggerPush() {{
  window.parent.postMessage({{type:'falconx', action:'push'}}, '*');
}}

// ── Graph node click → entity inspector ───────────────────────────────────────
// Receive click from pyvis iframe
window.addEventListener('message', function(ev) {{
  if (!ev.data) return;

  // From pyvis iframe
  if (ev.data.type === 'node_click') {{
    showEntity(ev.data);
  }}
}});

function showEntity(data) {{
  document.getElementById('noEntity').style.display = 'none';
  var card = document.getElementById('entityCard');
  card.style.display = 'block';

  var id    = data.nodeId   || '';
  var label = data.label    || '';
  var title = (data.title   || '').replace(/<[^>]*>/g, '');
  var ntype = id.startsWith('user_')  ? 'user'    :
              id.startsWith('tweet_') ? 'tweet'   :
              id.startsWith('hash_')  ? 'hashtag' : 'unknown';

  var badgeClass = 'badge-' + ntype;
  var badgeText  = ntype.toUpperCase();
  var displayLabel = label.replace(/\\n/g, ' ').substring(0, 48);

  card.innerHTML =
    '<div class="entity-card">' +
      '<div class="ent-header">' +
        '<span class="ent-badge ' + badgeClass + '">' + badgeText + '</span>' +
        '<span class="ent-name">' + displayLabel + '</span>' +
      '</div>' +
      '<div class="ent-body">' +
        '<div class="ent-field"><div class="ent-key">Node ID</div><div class="ent-val mono" style="font-size:9px;word-break:break-all">' + id + '</div></div>' +
        '<div class="ent-field"><div class="ent-key">Details</div><div class="ent-val">' + title + '</div></div>' +
      '</div>' +
    '</div>';
}}

// ── Inject click listener into pyvis iframe ────────────────────────────────────
function hookGraphFrame() {{
  var frames = document.querySelectorAll('.graph-frame iframe');
  frames.forEach(function(frame) {{
    try {{
      var win = frame.contentWindow;
      if (!win) return;
      // Poll until vis.js network is ready
      var attempts = 0;
      var poll = setInterval(function() {{
        attempts++;
        if (attempts > 60) {{ clearInterval(poll); return; }}
        var net = win.network;
        if (net) {{
          clearInterval(poll);
          net.on('click', function(params) {{
            if (params.nodes && params.nodes.length > 0) {{
              var nodeId = params.nodes[0];
              var node   = net.body.data.nodes.get(nodeId);
              if (node) {{
                window.postMessage({{
                  type:'node_click',
                  nodeId: nodeId,
                  label:  node.label  || '',
                  title:  node.title  || ''
                }}, '*');
              }}
            }}
          }});
        }}
      }}, 300);
    }} catch(e) {{}}
  }});
}}

// Run after page loads
window.addEventListener('load', function() {{
  setTimeout(hookGraphFrame, 800);
}});
</script>

</body>
</html>"""


# ════════════════════════════════════════════════════════════════════════════════
# HANDLE MESSAGES FROM THE HTML (via URL params hack — Streamlit limitation)
# We use a lightweight approach: hidden buttons + JS postMessage to parent
# which then clicks the appropriate hidden Streamlit button
# ════════════════════════════════════════════════════════════════════════════════

# JS bridge that lives OUTSIDE the iframe, in the Streamlit page itself
ST_BRIDGE = """
<script>
window.addEventListener('message', function(ev) {
  if (!ev.data || ev.data.type !== 'falconx') return;
  var d = ev.data;

  if (d.action === 'upload') {
    var inp = window.parent.document.querySelector('[data-testid="stFileUploader"] input[type=file]');
    if (inp) inp.click();
  }
  if (d.action === 'push') {
    var btns = window.parent.document.querySelectorAll('[data-testid="stButton"] button');
    btns.forEach(function(b){ if(b.innerText.trim()==='PUSH') b.click(); });
  }
  if (d.action === 'refresh') {
    var btns = window.parent.document.querySelectorAll('[data-testid="stButton"] button');
    btns.forEach(function(b){ if(b.innerText.trim()==='REFRESH') b.click(); });
  }
  if (d.action === 'theme') {
    // Store in sessionStorage, reload
    sessionStorage.setItem('falconx_theme', d.value);
    var btns = window.parent.document.querySelectorAll('[data-testid="stButton"] button');
    btns.forEach(function(b){ if(b.innerText.trim()==='THEME_'+d.value.toUpperCase()) b.click(); });
  }
});
</script>
"""
st.markdown(ST_BRIDGE, unsafe_allow_html=True)

# Theme buttons (hidden, triggered by JS)
col1, col2 = st.columns(2)
with col1:
    if st.button("THEME_LIGHT", key="theme_light"):
        st.session_state.theme = "light"
        st.rerun()
with col2:
    if st.button("THEME_DARK", key="theme_dark"):
        st.session_state.theme = "dark"
        st.rerun()

# Render the full HTML shell
components.html(HTML, height=1000, scrolling=False)

# ── JS to resize the component to fill the viewport ──────────────────────────
st.markdown("""
<script>
(function() {
  // Find the stCustomComponentV1 iframe and make it fill the viewport
  function resizeShell() {
    var frames = window.parent.document.querySelectorAll('iframe[title="stCustomComponentV1"]');
    frames.forEach(function(f) {
      f.style.height = (window.parent.innerHeight - 0) + 'px';
      f.style.width  = '100%';
      f.style.display = 'block';
      f.style.border = 'none';
    });
  }
  resizeShell();
  window.parent.addEventListener('resize', resizeShell);
  setTimeout(resizeShell, 500);
})();
</script>
""", unsafe_allow_html=True)
