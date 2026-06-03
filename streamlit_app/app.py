import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from functions.db_manager import init_db
from styles import inject

st.set_page_config(
    page_title="산업분석 자동화",
    page_icon="📊",
    layout="wide",
)

inject()

st.markdown("""
<style>
/* ── 랜딩 전용 스타일 ── */
.hero-title {
    font-size: 2.2rem; font-weight: 900; color: #1B3A6B;
    letter-spacing: -0.03em; line-height: 1.2;
    border-left: 5px solid #1B3A6B; padding-left: 16px;
    margin-bottom: 6px;
}
.hero-sub {
    font-size: 1rem; color: #64748B; font-weight: 400;
    padding-left: 21px; margin-bottom: 0;
}
.page-card {
    background: #ffffff;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 24px 24px 20px;
    min-height: 480px;
    display: flex;
    flex-direction: column;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    transition: box-shadow 0.2s, transform 0.2s;
}
.page-card:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.1); transform: translateY(-2px); }
.card-icon { font-size: 2.2rem; margin-bottom: 10px; }
.card-title { font-size: 1.1rem; font-weight: 800; color: #1B3A6B; margin-bottom: 6px; }
.card-desc { font-size: 0.84rem; color: #475569; line-height: 1.65; margin-bottom: 14px; flex: 1; }
.card-divider { border: none; border-top: 1px solid #F1F5F9; margin: 12px 0; }
.flow-label { font-size: 0.7rem; font-weight: 700; color: #94A3B8; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 8px; }
.mini-flow { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.mini-step {
    font-size: 0.73rem; font-weight: 600; color: #1B3A6B;
    background: #EEF4FF; padding: 4px 9px;
    border-radius: 4px; white-space: nowrap;
}
.mini-arrow { color: #CBD5E1; font-size: 0.7rem; font-weight: 700; }
.output-row { display: flex; align-items: center; gap: 6px; margin-top: 10px; }
.output-tag {
    font-size: 0.72rem; font-weight: 600; color: #64748B;
    background: #F8FAFC; border: 1px solid #E2E8F0;
    padding: 3px 8px; border-radius: 4px;
    white-space: nowrap; word-break: keep-all;
}
</style>
""", unsafe_allow_html=True)

init_db()

# ── 히어로 ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding: 1rem 0 1.5rem 0;">
    <div class="hero-title">산업분석 자동화</div>
    <div class="hero-sub">DART 증권신고서 기반  컨설팅 덱 자동 구성</div>
</div>
""", unsafe_allow_html=True)

st.markdown("### 메뉴 안내")
st.write("")

# ── 페이지 카드 3열 ───────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3, gap="medium")

with col1:
    st.markdown("""<div class="page-card">
    <div class="card-icon">📊</div>
    <div class="card-title">산업분석</div>
    <div class="card-desc">산업 키워드를 입력하면 관련 기업의 증권신고서를 자동으로 수집·분석합니다.
    컨설팅 덱 구성과 리서치 데이터를 엑셀로 출력합니다.</div>
    <hr class="card-divider">
    <div class="flow-label">사용 흐름</div>
    <div class="mini-flow">
        <span class="mini-step">① 키워드 입력</span>
        <span class="mini-arrow">›</span>
        <span class="mini-step">② 기업 선택</span>
        <span class="mini-arrow">›</span>
        <span class="mini-step">③ AI 분석</span>
        <span class="mini-arrow">›</span>
        <span class="mini-step">④ 엑셀 다운로드</span>
    </div>
    <div class="output-row">
        <span class="output-tag">덱 구성</span>
        <span class="output-tag">리서치 데이터</span>
        <span class="output-tag">.xlsx 출력</span>
    </div>
</div>""", unsafe_allow_html=True)
    st.write("")
    if st.button("산업분석 시작 →", key="go1", type="primary", use_container_width=True):
        st.switch_page("pages/1_산업분석.py")

with col2:
    st.markdown("""<div class="page-card">
    <div class="card-icon">🗺️</div>
    <div class="card-title">산업지도</div>
    <div class="card-desc">KRX 섹터 ETF 구성종목을 기반으로 한국 주요 산업과 기업을 트리맵으로 시각화합니다.
    섹터별 기업 현황을 한눈에 파악하고, 관심 기업을 바로 분석으로 연결할 수 있습니다.</div>
    <hr class="card-divider">
    <div class="flow-label">사용 흐름</div>
    <div class="mini-flow">
        <span class="mini-step">① 트리맵 탐색</span>
        <span class="mini-arrow">›</span>
        <span class="mini-step">② 섹터 클릭</span>
        <span class="mini-arrow">›</span>
        <span class="mini-step">③ 기업 확인</span>
        <span class="mini-arrow">›</span>
        <span class="mini-step">④ 분석 이동</span>
    </div>
    <div class="output-row">
        <span class="output-tag">섹터 트리맵</span>
        <span class="output-tag">기업 목록</span>
    </div>
</div>""", unsafe_allow_html=True)
    st.write("")
    if st.button("산업지도 보기 →", key="go2", type="primary", use_container_width=True):
        st.switch_page("pages/2_산업지도.py")

with col3:
    st.markdown("""<div class="page-card">
    <div class="card-icon">✅</div>
    <div class="card-title">기업분류검증</div>
    <div class="card-desc">특정 기업이 지정한 산업에 포함되는지 증권신고서·사업보고서 기반으로 판정합니다.
    산업분석 대상 기업 선정 전 적합성을 사전에 확인할 때 활용합니다.</div>
    <hr class="card-divider">
    <div class="flow-label">사용 흐름</div>
    <div class="mini-flow">
        <span class="mini-step">① 기업명 입력</span>
        <span class="mini-arrow">›</span>
        <span class="mini-step">② 산업명 입력</span>
        <span class="mini-arrow">›</span>
        <span class="mini-step">③ 검증 실행</span>
        <span class="mini-arrow">›</span>
        <span class="mini-step">④ 판정 결과</span>
    </div>
    <div class="output-row">
        <span class="output-tag">포함 / 미포함</span>
        <span class="output-tag">근거 세그먼트</span>
    </div>
</div>""", unsafe_allow_html=True)
    st.write("")
    if st.button("기업분류 검증 →", key="go3", type="primary", use_container_width=True):
        st.switch_page("pages/3_기업분류검증.py")

st.write("")
st.divider()
st.caption("데이터 출처: DART 전자공시시스템 · KRX 섹터 ETF (네이버 금융) · Anthropic Claude API")
