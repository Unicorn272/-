import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from datetime import date
from agents import filtering_agent, extraction_agent, analysis_agent
from functions.excel_generator import generate_excel

st.set_page_config(page_title="산업분석", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #1B3A6B; }
[data-testid="stSidebar"] * { color: #FFFFFF !important; }
</style>
""", unsafe_allow_html=True)

st.title("산업분석")
st.markdown("분석할 산업을 입력하면 증권신고서 기반 컨설팅 덱 구성과 리서치 데이터를 엑셀로 출력합니다.")
st.caption("기업 직접 지정: `ESS [삼성SDI, LG에너지솔루션]` 형식으로 입력하면 해당 기업만 분석합니다.")
st.divider()

if "step" not in st.session_state:
    st.session_state.step = "input"


def _reset():
    for key in list(st.session_state.keys()):
        del st.session_state[key]


# ── Step 1: 입력 ──────────────────────────────────────────────────────────────
if st.session_state.step == "input":
    query = st.text_input("", placeholder="예: ESS 배터리  /  메모리반도체 [삼성전자, SK하이닉스]", label_visibility="collapsed")
    if st.button("분석 시작", type="primary", disabled=not query):
        with st.spinner("관련 기업 및 신고서 조회 중..."):
            mode, companies, subsectors, warning = filtering_agent.run(query)

        if not companies:
            st.error("관련 신고서를 찾을 수 없습니다. 기업명이나 산업 키워드를 확인해주세요.")
            st.stop()

        st.session_state.update({
            "mode": mode,
            "companies": companies,
            "subsectors": subsectors or {},
            "query": query,
            "sec_warning": warning,
        })
        # Mode B(기업 직접 지정)면 기업 선택 화면 스킵
        st.session_state.step = "analyze" if mode == "B" else "select"
        st.rerun()


# ── Step 2: 기업 선택 (Mode A만) ─────────────────────────────────────────────
elif st.session_state.step == "select":
    subsectors: dict = st.session_state.subsectors
    query: str = st.session_state.query
    all_corp_names = [c for corps in subsectors.values() for c in corps]

    st.markdown(f"**`{query}`** 관련 기업 **{len(all_corp_names)}개** 발견. 분석할 기업을 선택하세요.")
    st.write("")

    select_all = st.checkbox("**전체 선택 / 해제**", value=True, key="select_all")
    st.divider()

    selected_corps: list[str] = []
    for label, corps in subsectors.items():
        st.markdown(f"##### {label}")
        cols = st.columns(min(len(corps), 5))
        for i, corp in enumerate(corps):
            with cols[i % 5]:
                if st.checkbox(corp, value=select_all, key=f"corp_{corp}"):
                    selected_corps.append(corp)
        st.write("")

    # ── 기업 직접 추가 ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("**기업 직접 추가**")
    add_col1, add_col2, _ = st.columns([4, 1, 7])
    with add_col1:
        manual_name = st.text_input(
            "기업명", placeholder="예: HD현대일렉트릭",
            label_visibility="collapsed", key="manual_corp_input"
        )
    with add_col2:
        add_clicked = st.button("추가", disabled=not manual_name)

    if add_clicked and manual_name:
        from functions.db_manager import get_connection
        from functions.dart_collector import find_corps_by_names, collect_by_corps

        corps = find_corps_by_names([manual_name])
        if not corps:
            st.error(f"'{manual_name}' 기업을 DART에서 찾을 수 없습니다.")
        else:
            with st.spinner(f"{corps[0]['corp_name']} 신고서 수집 중..."):
                collect_by_corps(corps)
            corp_name = corps[0]["corp_name"]
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT id, corp_code FROM filings WHERE corp_name=? ORDER BY filed_at DESC LIMIT 1",
                    [corp_name]
                ).fetchone()
            if not row:
                st.error(f"{corp_name} 신고서를 찾을 수 없습니다.")
            elif corp_name in all_corp_names:
                st.info(f"{corp_name}은 이미 목록에 있습니다.")
            else:
                new_entry = {"corp_name": corp_name, "corp_code": row["corp_code"],
                             "filing_id": row["id"], "revenue_share": None}
                st.session_state.companies.append(new_entry)
                subsectors.setdefault("직접 추가", []).append(corp_name)
                st.session_state.subsectors = subsectors
                st.success(f"{corp_name} 추가됨")
                st.rerun()

    st.divider()
    n = len(selected_corps)
    col1, col2 = st.columns([2, 2])
    with col1:
        if st.button(f"분석 진행 ({n}개)", type="primary", disabled=n == 0):
            st.session_state.companies = [
                c for c in st.session_state.companies
                if c["corp_name"] in selected_corps
            ]
            st.session_state.step = "analyze"
            st.rerun()
    with col2:
        if st.button("다시 입력"):
            _reset()
            st.rerun()


# ── Step 3 & 4: 분석 실행 + 결과 표시 ─────────────────────────────────────────
elif st.session_state.step in ("analyze", "done"):
    query: str = st.session_state.query

    if "analysis" not in st.session_state:
        companies = st.session_state.companies
        if st.session_state.get("sec_warning"):
            st.warning(st.session_state.sec_warning)

        corp_codes = [c["corp_code"] for c in companies if c.get("corp_code")]

        with st.status("분석 중...", expanded=True) as status:
            st.write("② 투자위험요소 텍스트 수집 중...")
            extracted = extraction_agent.run(companies, mode=st.session_state.mode)
            corp_list = [c["corp_name"] for c in extracted.get("corp_filings", [])]
            st.write(f"✅ {len(corp_list)}개 신고서 수집 완료: {corp_list}")

            st.write("③ 덱 구성 및 리서치 데이터 작성 중...")
            analysis = analysis_agent.run(extracted, query, corp_codes)
            st.write("✅ 분석 완료")

            st.write("④ 엑셀 생성 중...")
            excel_bytes = generate_excel(analysis, query, date.today().strftime("%Y.%m.%d"))
            status.update(label="분석 완료", state="complete")

        st.session_state.analysis = analysis
        st.session_state.excel_bytes = excel_bytes
        st.session_state.step = "done"

    analysis = st.session_state.analysis
    st.divider()

    tab1, tab2 = st.tabs(["덱 구성", "리서치 데이터"])

    with tab1:
        for sec in analysis.get("sections", []):
            st.markdown(f"#### Section {sec['section_no']}: {sec['section_title']}")
            for ch in sec.get("chapters", []):
                with st.container(border=True):
                    st.markdown(f"**장 {ch['no']}. {ch['title']}**")
                    st.caption(ch.get("description", ""))
            st.info(sec.get("key_message", ""))
            st.write("")

    with tab2:
        st.info("리서치 데이터는 아래 엑셀 파일에서 확인하세요.")

    st.divider()
    col1, col2 = st.columns([2, 5])
    with col1:
        st.download_button(
            label="📊 엑셀 다운로드",
            data=st.session_state.excel_bytes,
            file_name=f"{query}_산업분석_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col2:
        if st.button("새 분석 시작"):
            _reset()
            st.rerun()
