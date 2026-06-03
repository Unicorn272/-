import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from datetime import date
from agents import filtering_agent, extraction_agent, analysis_agent
from agents.chat_agent import stream_response
from functions.excel_generator import generate_excel
from styles import inject, step_bar

st.set_page_config(page_title="산업분석", layout="wide")
inject()

st.title("산업분석")
st.markdown("분석할 산업을 입력하면 증권신고서 기반 컨설팅 덱 구성과 리서치 데이터를 엑셀로 출력합니다.")
st.caption("기업 직접 지정: `ESS [삼성SDI, LG에너지솔루션]` 형식으로 입력하면 해당 기업만 분석합니다.")
st.divider()

if "step" not in st.session_state:
    st.session_state.step = "input"


def _reset():
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def _clear_checkboxes():
    for k in list(st.session_state.keys()):
        if k.startswith("corp_check_"):
            del st.session_state[k]


# ── 스텝 표시 ─────────────────────────────────────────────────────────────────
st.markdown(step_bar(st.session_state.step), unsafe_allow_html=True)

# ── Step 1: 입력 ──────────────────────────────────────────────────────────────
if st.session_state.step == "input":
    default_query = st.session_state.pop("prefill_query", "")
    query = st.text_input("", placeholder="예: ESS 배터리  /  메모리반도체 [삼성전자, SK하이닉스]", label_visibility="collapsed", value=default_query)
    if st.button("분석 시작", type="primary", disabled=not query):
        with st.spinner("관련 기업 및 신고서 조회 중..."):
            mode, companies, warning, etf_sources, purposes = filtering_agent.run(query)

        if not companies:
            st.error("관련 신고서를 찾을 수 없습니다. 기업명이나 산업 키워드를 확인해주세요.")
            st.stop()

        st.session_state.update({
            "mode": mode,
            "companies": companies,
            "query": query,
            "sec_warning": warning,
            "etf_sources": etf_sources,
            "purposes": purposes,
        })
        st.session_state.step = "analyze" if mode == "B" else "select"
        st.rerun()


# ── Step 2: 기업 선택 (Mode A만) ─────────────────────────────────────────────
elif st.session_state.step == "select":
    query: str = st.session_state.query
    companies_list: list = st.session_state.companies
    purposes: dict | None = st.session_state.get("purposes")
    etf_sources: list = st.session_state.get("etf_sources", [])

    if etf_sources:
        st.info(f"**출처**: {' · '.join(etf_sources)}")
    else:
        st.caption("ETF 매핑 없음 — Claude 지식 + 뉴스 기반 선별")

    st.markdown(f"**`{query}`** 산업의 관련 기업입니다. 분석할 기업을 선택하세요.")
    st.write("")

    if "selected_corps_set" not in st.session_state:
        st.session_state.selected_corps_set = set()

    # ── 목적 프리셋 카드 ────────────────────────────────────────────────────────
    if purposes:
        st.markdown("**분석 관점** — 관점을 선택하면 해당 기업이 자동으로 체크됩니다.")
        n_p = min(len(purposes), 4)
        p_cols = st.columns(n_p, gap="small")
        for i, (label, corps) in enumerate(purposes.items()):
            with p_cols[i % n_p]:
                with st.container(border=True):
                    st.markdown(f"**{label}**")
                    st.caption("  \n".join(f"· {c}" for c in corps))
                    if st.button("이 관점으로 선택", key=f"preset_{i}",
                                 use_container_width=True, type="primary"):
                        st.session_state.selected_corps_set = set(corps)
                        _clear_checkboxes()
                        st.rerun()
        st.write("")

    # ── 전체 기업 체크박스 ──────────────────────────────────────────────────────
    all_corp_names = list(dict.fromkeys(c["corp_name"] for c in companies_list))
    c1, c2, _ = st.columns([1, 1, 8])
    with c1:
        if st.button("전체 선택", key="sel_all"):
            st.session_state.selected_corps_set = set(all_corp_names)
            _clear_checkboxes()
            st.rerun()
    with c2:
        if st.button("전체 해제", key="desel_all"):
            st.session_state.selected_corps_set = set()
            _clear_checkboxes()
            st.rerun()
    st.write("")
    cols = st.columns(min(len(all_corp_names), 5))
    for i, corp in enumerate(all_corp_names):
        with cols[i % 5]:
            checked = st.checkbox(
                corp,
                value=corp in st.session_state.selected_corps_set,
                key=f"corp_check_{corp}",
            )
            if checked:
                st.session_state.selected_corps_set.add(corp)
            else:
                st.session_state.selected_corps_set.discard(corp)

    selected_corps: list[str] = list(st.session_state.selected_corps_set)
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
        from functions.dart_collector import find_corps_by_names
        corps = find_corps_by_names([manual_name])
        if not corps:
            st.error(f"'{manual_name}' 기업을 DART에서 찾을 수 없습니다.")
        else:
            corp = corps[0]
            corp_name = corp["corp_name"]
            new_entry = {"corp_name": corp_name, "corp_code": corp["corp_code"],
                         "stock_code": corp.get("stock_code", ""), "filing_id": None, "revenue_share": None}
            st.session_state.companies.append(new_entry)
            st.session_state.selected_corps_set.add(corp_name)
            st.success(f"{corp_name} 추가됨")
            st.rerun()

    st.divider()
    n = len(selected_corps)
    col1, col2 = st.columns([2, 2])
    with col1:
        if st.button(f"분석 진행 ({n}개)", type="primary", disabled=n == 0):
            selected = [c for c in st.session_state.companies if c["corp_name"] in selected_corps]
            with st.spinner(f"{n}개 기업 신고서 수집 중..."):
                from functions.dart_collector import collect_by_corps
                from agents.filtering_agent import _query_db_by_corp_codes
                corp_codes = [c["corp_code"] for c in selected if c.get("corp_code")]
                corps_info = [{"corp_code": c["corp_code"], "corp_name": c["corp_name"],
                               "stock_code": c.get("stock_code", "")} for c in selected]
                collect_by_corps(corps_info)
                companies_with_filings = _query_db_by_corp_codes(corp_codes)
            if not companies_with_filings:
                st.error("수집된 신고서가 없습니다.")
                st.stop()
            st.session_state.companies = companies_with_filings
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

        corp_codes = list(dict.fromkeys(c["corp_code"] for c in companies if c.get("corp_code")))

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
        for sec_idx, sec in enumerate(analysis.get("sections", []), 1):
            chapters = sec.get("chapters", [])
            sec_title = sec.get("section_title", "")
            key_msg = sec.get("key_message", "")

            st.markdown(f'<span class="section-badge">Section {sec_idx}</span>', unsafe_allow_html=True)
            st.markdown(f'<div class="section-heading">{sec_title}</div>', unsafe_allow_html=True)

            n_cols = min(len(chapters), 3)
            if n_cols > 0:
                cols = st.columns(n_cols)
                for i, ch in enumerate(chapters):
                    with cols[i % n_cols]:
                        title = str(ch.get("title", "")).replace("<", "&lt;").replace(">", "&gt;")
                        desc = str(ch.get("description", "")).replace("<", "&lt;").replace(">", "&gt;")
                        st.markdown(f"""<div class="slide-card">
                            <div class="slide-no">장 {ch.get('no', i+1)}</div>
                            <div class="slide-title">{title}</div>
                            <div class="slide-desc">{desc}</div>
                        </div>""", unsafe_allow_html=True)

            if key_msg:
                safe_km = str(key_msg).replace("<", "&lt;").replace(">", "&gt;")
                st.markdown(f'<div class="key-message">💡 {safe_km}</div>', unsafe_allow_html=True)

            st.write("")
            st.divider()

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

    # ── 챗봇 ─────────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("💬 분석 결과 질의")
    st.caption("신고서 데이터와 실시간 시장 데이터를 기반으로 투자 시사점을 답변합니다.")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # 빠른 질문 버튼
    companies_in_analysis = [c["corp_name"] for c in st.session_state.get("companies", [])]
    corp_label = companies_in_analysis[0] if len(companies_in_analysis) == 1 else "각 기업"

    q_col1, q_col2, q_col3 = st.columns(3)
    quick_prompt = None
    with q_col1:
        if st.button(f"이 정보가 {corp_label} 실적에 어떤 의미인가요?", use_container_width=True):
            quick_prompt = f"이 정보가 {corp_label} 실적에 어떤 의미인가요?"
    with q_col2:
        if st.button("경쟁사 대비 각 기업의 포지션은?", use_container_width=True):
            quick_prompt = "경쟁사 대비 각 기업의 포지션은?"
    with q_col3:
        if st.button("시장이 아직 반영 못 한 리스크나 기회는?", use_container_width=True):
            quick_prompt = "시장이 아직 반영 못 한 리스크나 기회는?"

    # 채팅 히스토리
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 입력 처리 (직접 입력 또는 빠른 질문)
    user_input = st.chat_input("질문을 입력하세요...") or quick_prompt
    if user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            api_messages = [{"role": m["role"], "content": m["content"]}
                            for m in st.session_state.chat_messages]
            response = st.write_stream(
                stream_response(analysis, query, api_messages)
            )
        st.session_state.chat_messages.append({"role": "assistant", "content": response})
        st.rerun()
