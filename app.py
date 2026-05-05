"""
app.py — FluentUp navigation hub

Run locally:
    streamlit run app.py

Pages:
  • Home         (pages/0_Home.py)      — landing, no sidebar
  • Speaking     (pages/1_Speaking.py)  — IELTS speaking practice
  • Listening    (pages/2_Listening.py) — IELTS listening practice
"""
import streamlit as st

st.set_page_config(
    page_title="FluentUp",
    page_icon="🎯",
    layout="wide",
)

pg = st.navigation(
    {
        "FluentUp": [
            st.Page("pages/0_Home.py",      title="Home",      icon="🏠", default=True),
        ],
        "Practice": [
            st.Page("pages/1_Speaking.py",  title="Speaking",  icon="🗣️"),
            st.Page("pages/2_Listening.py", title="Listening", icon="🎧"),
        ],
    }
)
pg.run()
