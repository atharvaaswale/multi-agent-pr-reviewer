"""Visual design system for the Streamlit frontend.

One dark, enterprise-grade theme lives here: the severity/accent palettes
and a single block of CSS. Keeping it in one place lets the component code
stay focused on structure rather than styling.
"""

import streamlit as st

# --------------------------------------------------------------------------
# Palette -- also referenced from Python when colors must be inlined into
# HTML (severity badges, metric values, status dots).
# --------------------------------------------------------------------------
ACCENT = "#5b8def"
OK_COLOR = "#3fb950"
WARN_COLOR = "#d4a72c"
DOWN_COLOR = "#f0616d"
MUTED_COLOR = "#646b7a"

# Severity palette -- muted, desaturated tones for a professional look.
SEVERITY_COLORS = {
    "critical": "#f0616d",  # red
    "high": "#e8924a",      # orange
    "medium": "#d4a72c",    # amber
    "low": "#5b8def",       # blue
    "info": "#8b909e",      # gray
}

# Small colored markers used only inside Streamlit expander labels, where
# rich HTML is not available.
SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "⚪",
}

# Display order, highest severity first.
SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

CATEGORY_EMOJI = {
    "security": "🔐",
    "architecture": "🏛",
    "quality": "✨",
    "performance": "⚡",
    "maintainability": "🔧",
}

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg:#0b0d12;
  --surface:#12151c;
  --surface-2:#171b24;
  --border:#262b36;
  --border-hi:#39404e;
  --text:#e6e8ee;
  --text-muted:#9aa0ac;
  --text-dim:#646b7a;
  --accent:#5b8def;
  --ok:#3fb950;
  --warn:#d4a72c;
  --down:#f0616d;
}

/* ---- base ---- */
html, body, [data-testid="stAppViewContainer"], .stApp {
  font-family:'Inter',-apple-system,'Segoe UI',Roboto,sans-serif;
}
[data-testid="stAppViewContainer"] { background:var(--bg); }
[data-testid="stHeader"] { display:none; }
#MainMenu, footer { visibility:hidden; }

.block-container {
  padding-top:1.6rem; padding-bottom:3rem; max-width:1180px;
}
[data-testid="stVerticalBlock"] { gap:.75rem; }

code, kbd, pre, [data-testid="stCodeBlock"], [data-testid="stCodeBlock"] * {
  font-family:'JetBrains Mono',ui-monospace,monospace !important;
}
h1, h2, h3, h4 { letter-spacing:-.012em; }

::-webkit-scrollbar { width:9px; height:9px; }
::-webkit-scrollbar-thumb { background:#2c323e; border-radius:6px; }
::-webkit-scrollbar-track { background:transparent; }

/* ---- top navbar ---- */
.navbar {
  display:flex; align-items:center; justify-content:space-between;
  gap:1rem; flex-wrap:wrap;
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:11px;
  padding:.62rem .9rem;
  margin-bottom:1.05rem;
}
.nav-left { display:flex; align-items:center; gap:.62rem; }
.nav-mark {
  width:28px; height:28px; border-radius:8px;
  background:rgba(91,141,239,.14);
  border:1px solid rgba(91,141,239,.34);
  color:var(--accent);
  display:flex; align-items:center; justify-content:center;
  font-size:.86rem; font-weight:700; flex:none;
}
.nav-title { font-size:1.02rem; font-weight:650; color:var(--text); line-height:1.2; }
.nav-sub { font-size:.73rem; color:var(--text-dim); }
.nav-right { display:flex; align-items:center; gap:.42rem; flex-wrap:wrap; }
.nav-chip {
  display:inline-flex; align-items:center; gap:.42rem;
  background:var(--surface-2); border:1px solid var(--border);
  border-radius:7px; padding:.28rem .56rem; font-size:.76rem; color:var(--text);
}
.nav-chip .k {
  font-size:.61rem; font-weight:700; letter-spacing:.07em;
  text-transform:uppercase; color:var(--text-dim);
}
.nav-chip .v { font-family:'JetBrains Mono',monospace; font-size:.73rem; }
.nav-status {
  display:inline-flex; align-items:center; gap:.42rem;
  border-radius:7px; padding:.28rem .58rem; font-size:.76rem; font-weight:600;
}
.nav-status.up   { background:rgba(63,185,80,.12);  border:1px solid rgba(63,185,80,.32);  color:var(--ok); }
.nav-status.down { background:rgba(240,97,109,.12); border:1px solid rgba(240,97,109,.32); color:var(--down); }
.dot { width:7px; height:7px; border-radius:50%; display:inline-block; flex:none; }

/* ---- section label ---- */
.section-title {
  font-size:.72rem; font-weight:700; letter-spacing:.09em;
  text-transform:uppercase; color:var(--text-dim);
  margin:.5rem 0 .55rem;
}

/* ---- pr header ---- */
.pr-head { display:flex; align-items:baseline; gap:.5rem; flex-wrap:wrap; }
.pr-num { font-family:'JetBrains Mono',monospace; font-size:.82rem; color:var(--text-dim); }
.pr-title { font-size:1.12rem; font-weight:650; color:var(--text); }

/* ---- metric grid ---- */
.mgrid { display:grid; gap:.7rem; margin:.15rem 0 .3rem; }
.mgrid-4 { grid-template-columns:repeat(4,1fr); }
.mgrid-3 { grid-template-columns:repeat(3,1fr); }
.metric-card {
  background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:.8rem .9rem;
}
.metric-card .mc-label {
  font-size:.65rem; font-weight:700; letter-spacing:.08em;
  text-transform:uppercase; color:var(--text-dim);
}
.metric-card .mc-value {
  font-size:1.6rem; font-weight:700; color:var(--text);
  margin-top:.22rem; line-height:1.14;
}
.metric-card .mc-sub { font-size:.71rem; color:var(--text-muted); margin-top:.28rem; }
.mc-bar {
  height:4px; border-radius:3px; background:var(--surface-2);
  margin-top:.5rem; overflow:hidden;
}
.mc-bar > span { display:block; height:100%; border-radius:3px; }

/* ---- badges ---- */
.sev-badge {
  display:inline-block; font-size:.65rem; font-weight:700;
  letter-spacing:.05em; text-transform:uppercase;
  padding:.16rem .46rem; border-radius:5px; margin-right:.34rem;
}
.cat-badge {
  display:inline-block; font-size:.65rem; font-weight:600;
  letter-spacing:.04em; text-transform:uppercase;
  padding:.16rem .46rem; border-radius:5px;
  background:var(--surface-2); border:1px solid var(--border);
  color:var(--text-muted); margin-right:.34rem;
}

/* ---- findings ---- */
.finding-top {
  display:flex; align-items:center; justify-content:space-between;
  gap:.6rem; flex-wrap:wrap; margin:.15rem 0 .6rem;
}
.finding-loc {
  font-family:'JetBrains Mono',monospace; font-size:.74rem;
  color:var(--text-muted);
  background:var(--surface-2); border:1px solid var(--border);
  border-radius:5px; padding:.14rem .46rem;
}
.kv-label {
  font-size:.65rem; font-weight:700; letter-spacing:.08em;
  text-transform:uppercase; color:var(--text-dim);
  margin:.75rem 0 .3rem;
}
.sev-chips { display:flex; gap:.42rem; flex-wrap:wrap; margin:.15rem 0 .3rem; }
.sev-chip {
  display:inline-flex; align-items:center; gap:.38rem;
  font-size:.73rem; font-weight:600; color:var(--text-muted);
  background:var(--surface); border:1px solid var(--border);
  border-radius:7px; padding:.22rem .54rem;
}
.sev-chip b { font-weight:700; }

/* ---- status strip ---- */
.status-strip {
  display:flex; align-items:center; gap:.55rem; flex-wrap:wrap;
  border-radius:9px; padding:.6rem .82rem; font-size:.84rem;
  border:1px solid var(--border); background:var(--surface);
}
.status-strip .ss-label { font-weight:650; }
.status-strip .ss-note { color:var(--text-muted); font-size:.79rem; }

/* ---- empty state ---- */
.empty {
  border:1px dashed var(--border); border-radius:11px;
  background:var(--surface); padding:1.5rem 1.4rem;
}
.empty h3 { margin:0 0 .35rem; font-size:1rem; color:var(--text); }
.empty p  { margin:0; color:var(--text-muted); font-size:.85rem; line-height:1.55; }
.agent-row { display:grid; grid-template-columns:repeat(3,1fr); gap:.6rem; margin-top:1.1rem; }
.agent-card {
  background:var(--surface-2); border:1px solid var(--border);
  border-radius:9px; padding:.7rem .82rem;
}
.agent-card .ac-name { font-size:.84rem; font-weight:650; color:var(--text); }
.agent-card .ac-desc { font-size:.75rem; color:var(--text-muted); margin-top:.22rem; line-height:1.45; }

/* ---- expander (finding accordion) ---- */
[data-testid="stExpander"] details {
  border:1px solid var(--border) !important;
  border-radius:9px !important;
  background:var(--surface) !important;
}
[data-testid="stExpander"] details:hover { border-color:var(--border-hi) !important; }
[data-testid="stExpander"] summary { padding:.5rem .75rem; }
[data-testid="stExpander"] summary:hover { color:var(--accent); }

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"] { gap:.12rem; border-bottom:1px solid var(--border); }
.stTabs [data-baseweb="tab"] {
  height:36px; padding:0 .85rem; font-size:.83rem; color:var(--text-muted);
}
.stTabs [data-baseweb="tab"]:hover { color:var(--text); }
.stTabs [aria-selected="true"] { color:var(--text) !important; font-weight:600; }
.stTabs [data-baseweb="tab-panel"] { padding-top:.85rem; }

/* ---- inputs / buttons ---- */
.stButton button, .stLinkButton a {
  border-radius:7px !important; font-size:.84rem !important; font-weight:600 !important;
}
[data-testid="stTextInput"] input { background:var(--surface-2); font-size:.88rem; }

/* ---- sidebar ---- */
[data-testid="stSidebar"] { background:var(--surface); border-right:1px solid var(--border); }
[data-testid="stSidebar"] .block-container { padding-top:1.4rem; }
.side-brand { display:flex; align-items:center; gap:.55rem; }
.side-brand .sb-name { font-size:.92rem; font-weight:650; color:var(--text); }
.side-desc { font-size:.78rem; color:var(--text-muted); line-height:1.55; margin:.6rem 0 .1rem; }
.side-h {
  font-size:.66rem; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; color:var(--text-dim); margin:1.25rem 0 .5rem;
}
.side-row { display:flex; align-items:baseline; gap:.5rem; font-size:.79rem; padding:.16rem 0; }
.side-row .sr-k { color:var(--text); font-weight:600; }
.side-row .sr-v { color:var(--text-dim); font-size:.73rem; }
.step {
  display:flex; gap:.55rem; align-items:flex-start;
  font-size:.78rem; color:var(--text-muted); padding:.2rem 0;
}
.step-n {
  flex:none; width:18px; height:18px; border-radius:5px;
  background:var(--surface-2); border:1px solid var(--border);
  font-size:.63rem; font-weight:700; color:var(--text-dim);
  display:flex; align-items:center; justify-content:center;
}
.tag {
  display:inline-block; font-family:'JetBrains Mono',monospace;
  font-size:.69rem; color:var(--text-muted);
  background:var(--surface-2); border:1px solid var(--border);
  border-radius:5px; padding:.12rem .4rem; margin:0 .26rem .3rem 0;
}
.side-foot {
  margin-top:1.4rem; padding-top:.8rem; border-top:1px solid var(--border);
  font-size:.71rem; color:var(--text-dim);
}

/* ---- footer ---- */
.app-footer {
  text-align:center; color:var(--text-dim); font-size:.74rem;
  margin-top:2.4rem; padding-top:1rem; border-top:1px solid var(--border);
}

/* ---- laptop / small screens ---- */
@media (max-width:900px) {
  .mgrid-4 { grid-template-columns:repeat(2,1fr); }
  .mgrid-3, .agent-row { grid-template-columns:1fr; }
}
</style>
"""


def inject_css() -> None:
    """Apply the custom stylesheet. Call once, after ``set_page_config``."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
