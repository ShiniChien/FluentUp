"""
app.py — FluentUp navigation hub

Run locally:
    streamlit run app.py

Defines the two-page navigation:
  • Speaking Practice  (pages/1_FluentUp.py)
  • EchoLab Listening  (pages/2_EchoLab.py)
"""
import streamlit as st

st.set_page_config(
    page_title="FluentUp",
    page_icon="🎯",
    layout="wide",
)

pg = st.navigation(
    {
        "Practice": [
            st.Page("pages/1_FluentUp.py", title="FluentUp", icon="🗣️"),
            st.Page("pages/2_EchoLab.py",  title="EchoLab", icon="🎧"),
        ]
    }
)
pg.run()
