"""pages/6_Practice.py — Practice: Dictation, Shadowing, Vocab Flashcards."""
from __future__ import annotations

import streamlit as st

from core.auth import is_logged_in
from core.practice.ui import main

if not is_logged_in():
    st.error("Bạn chưa đăng nhập. Vui lòng quay lại trang chủ.")
    if st.button("Về trang chủ"):
        st.switch_page("pages/0_Home.py")
else:
    main()
