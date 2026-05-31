import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
from functions.db_manager import get_connection, init_db

st.set_page_config(page_title="DB 관리", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #1B3A6B; }
[data-testid="stSidebar"] * { color: #FFFFFF !important; }
</style>
""", unsafe_allow_html=True)

init_db()

st.title("DB 관리")
st.divider()

# 현황 카드
with get_connection() as conn:
    filing_count  = conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
    segment_count = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    company_count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]

col1, col2, col3 = st.columns(3)
with col1:
    with st.container(border=True): st.metric("신고서", f"{filing_count}건")
with col2:
    with st.container(border=True): st.metric("사업부 데이터", f"{segment_count}건")
with col3:
    with st.container(border=True): st.metric("기업 레지스트리", f"{company_count}개")

st.divider()

# 신고서 목록
st.markdown("### 신고서 목록")
with get_connection() as conn:
    rows = conn.execute(
        "SELECT corp_name, report_type, filed_at, doc_url FROM filings ORDER BY filed_at DESC LIMIT 100"
    ).fetchall()

if rows:
    df = pd.DataFrame(rows, columns=["회사명", "신고서 종류", "제출일", "문서 URL"])
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.caption("데이터가 없습니다. 위에서 수집을 먼저 실행하세요.")
