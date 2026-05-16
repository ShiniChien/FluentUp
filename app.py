# streamlit run app.py
import streamlit as st

from core.async_utils import run_async
from core.shared import load_secrets, get_store
from core.vocab_sidebar import render_vocab_sidebar

st.set_page_config(
    page_title="FluentUp",
    page_icon="🎯",
    layout="wide",
)

nav_pages = st.navigation(
    {
        "FluentUp": [
            st.Page("pages/0_Home.py",      title="Home",      icon="🏠", default=True),
        ],
        "Skills": [
            st.Page("pages/1_Speaking.py",  title="Speaking",  icon="🗣️"),
            st.Page("pages/2_Listening.py", title="Listening", icon="🎧"),
            st.Page("pages/4_Writing.py",   title="Writing",   icon="✍️"),
            st.Page("pages/5_Reading.py",   title="Reading",   icon="📖"),
            st.Page("pages/3_Chat.py",      title="Live Chat", icon="💬"),
        ],
        "Practice": [
            st.Page("pages/6_Practice.py",  title="Practice",  icon="🏋️"),
        ],
    }
)

_secrets = load_secrets()
_store   = get_store(_secrets)
if _store and "vocab_indexes_ensured" not in st.session_state:
    run_async(_store.ensure_indexes())
    st.session_state["vocab_indexes_ensured"] = True

render_vocab_sidebar(_store)

nav_pages.run()
