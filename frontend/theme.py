"""Shared visual theme -- a dark teal-navy body with light-blue accents ("Ice" palette),
injected via CSS since Streamlit doesn't expose this kind of theming natively. Call
apply_theme() once near the top of every page, right after st.set_page_config() (Streamlit
re-runs each page's script on navigation, so the injection has to happen on every page, not
just app.py).

Note: the browser-tab "Deploy" toolbar and the page-icon glyphs next to sidebar nav entries are
Streamlit Cloud/Streamlit-native chrome, not something a theme can restyle from here."""

import streamlit as st

_CSS = """
<style>
[data-testid="stAppViewContainer"] {
    background: linear-gradient(180deg, #173347 0%, #102638 55%, #0B1D2C 100%);
}

[data-testid="stHeader"] {
    background: transparent;
}

section[data-testid="stSidebar"] {
    background: #0A1B2A;
    border-right: 1px solid rgba(125, 185, 235, 0.15);
}

section[data-testid="stSidebar"] * {
    color: #CFE6F7 !important;
}

/* Highlight the active page in the sidebar nav. */
section[data-testid="stSidebar"] [aria-current="page"] {
    background: #1C3A54 !important;
    border-radius: 8px;
}
section[data-testid="stSidebar"] [aria-current="page"] * {
    color: #FFFFFF !important;
}

/* Card-style bordered containers (st.container(border=True), expanders, forms). */
div[data-testid="stVerticalBlockBorderWrapper"],
div[data-testid="stExpander"],
div[data-testid="stForm"] {
    background: rgba(125, 185, 235, 0.08);
    border: 1px solid rgba(125, 185, 235, 0.25);
    border-radius: 14px;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div {
    padding: 0.5rem 0.25rem;
}

h1, h2, h3, h4, h5, h6, p, li, label, span {
    color: #E8F3FB;
}

.stButton > button, .stDownloadButton > button {
    background: #7DB9EB;
    color: #0B1F2E;
    border: none;
    border-radius: 10px;
    font-weight: 700;
    transition: background 0.2s ease, transform 0.15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: #A3D0F5;
    color: #0B1F2E;
    transform: translateY(-1px);
}

[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-baseweb="select"] > div {
    background: #173248 !important;
    color: #E8F3FB !important;
    border: 1px solid rgba(125, 185, 235, 0.5) !important;
    border-radius: 10px !important;
}

/* Alert boxes (st.success/info/warning/error) -- light-to-medium blue gradient, dark text so
   it stays readable on the near-white end of the gradient. */
div[data-testid="stAlert"] {
    border-radius: 10px;
    border: none;
}
div[data-testid="stAlertContentSuccess"],
div[data-testid="stAlertContentInfo"] {
    background: linear-gradient(90deg, #4A7FC9 0%, #DCEBFA 100%);
    border-radius: 10px;
}
div[data-testid="stAlertContentSuccess"] *,
div[data-testid="stAlertContentInfo"] * {
    color: #0B1F2E !important;
}
div[data-testid="stAlertContentWarning"] {
    background: linear-gradient(90deg, #C9974A 0%, #FBEEDC 100%);
    border-radius: 10px;
}
div[data-testid="stAlertContentWarning"] * {
    color: #2E1F0B !important;
}
div[data-testid="stAlertContentError"] {
    background: linear-gradient(90deg, #C94A4A 0%, #FBDCDC 100%);
    border-radius: 10px;
}
div[data-testid="stAlertContentError"] * {
    color: #2E0B0B !important;
}

div[data-testid="stMetric"] {
    background: rgba(125, 185, 235, 0.08);
    border: 1px solid rgba(125, 185, 235, 0.25);
    border-radius: 12px;
    padding: 0.75rem 1rem;
}
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
    color: #E8F3FB !important;
}
</style>
"""


def apply_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
