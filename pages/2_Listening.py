"""pages/2_Listening.py — Listening Practice (entry point)"""
import streamlit as st
from core.auth import is_logged_in
from core.listening.ui import main

if not is_logged_in():
    st.error("Bạn chưa đăng nhập. Vui lòng quay lại trang chủ để đăng nhập.")
    if st.button("Về trang chủ"):
        st.switch_page("pages/0_Home.py")
else:
    main()
