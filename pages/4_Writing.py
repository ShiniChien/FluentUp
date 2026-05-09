"""pages/4_Writing.py — Writing Practice (entry point)"""
import time

import streamlit as st
from core.auth import is_logged_in
from core.writing.ui import main

if not is_logged_in():
    st.error("Bạn chưa đăng nhập. Đang chuyển hướng về trang chủ…")
    time.sleep(2)
    st.switch_page("pages/0_Home.py")
else:
    main()
