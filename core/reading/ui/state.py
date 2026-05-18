from __future__ import annotations

import streamlit as st


def init_state() -> None:
    defaults: dict = {
        "reading_phase":            "idle",
        "reading_topic":            "World",
        "reading_articles_list":    [],       # list[ArticleEntry] from RSS
        "reading_selected":         None,     # dict: title, link, pub_date, topic
        "reading_doc_id":           None,
        "reading_article":          None,     # dict with llm_content, title, link, etc.
        "reading_questions":        None,     # dict: requirement, questions list
        "reading_answers":          {},
        "reading_score":            None,
        "reading_error":            None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_state() -> None:
    for k in (
        "reading_phase", "reading_articles_list", "reading_selected",
        "reading_doc_id", "reading_article", "reading_questions",
        "reading_answers", "reading_score", "reading_error",
    ):
        st.session_state[k] = {
            "reading_phase":         "idle",
            "reading_articles_list": [],
            "reading_selected":      None,
            "reading_doc_id":        None,
            "reading_article":       None,
            "reading_questions":     None,
            "reading_answers":       {},
            "reading_score":         None,
            "reading_error":         None,
        }.get(k)
