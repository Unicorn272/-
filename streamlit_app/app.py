import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from functions.db_manager import init_db

st.set_page_config(
    page_title="산업분석",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
[data-testid="stSidebar"] {
    background-color: #1B3A6B;
}
[data-testid="stSidebar"] * {
    color: #FFFFFF !important;
}
[data-testid="stSidebarNav"] a {
    color: #FFFFFF !important;
}
</style>
""", unsafe_allow_html=True)

init_db()

st.title("산업분석 자동화")
st.markdown("사이드바에서 메뉴를 선택하세요.")
