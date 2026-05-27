import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from datetime import date
from agents import filtering_agent, extraction_agent, analysis_agent
from functions.ppt_generator import generate_ppt

st.set_page_config(page_title="산업분석", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #1B3A6B; }
[data-testid="stSidebar"] * { color: #FFFFFF !important; }
</style>
""", unsafe_allow_html=True)

st.title("산업분석")
st.markdown("분석할 산업을 입력하면 신고서 기반 Porter 5 Forces + PESTEL 분석을 자동으로 수행합니다.")
st.divider()

query = st.text_input("", placeholder="예: 전기차 MLCC", label_visibility="collapsed")
run_btn = st.button("분석 시작", type="primary", disabled=not query)

if run_btn and query:
    companies = None
    extracted = None
    analysis = None
    ppt_bytes = None

    with st.status("분석 중...", expanded=True) as status:
        st.write("① 관련 신고서 조회 중...")
        companies, sec_warning = filtering_agent.run(query)
        if not companies:
            st.error("관련 신고서를 찾을 수 없습니다. DB에 데이터가 없거나 키워드를 확인해주세요.")
            st.stop()
        if sec_warning:
            st.warning(sec_warning)
        st.write(f"✅ {len(companies)}개 신고서 선별 완료")

        st.write("② 투자위험요소 추출 중...")
        extracted = extraction_agent.run(companies, query)
        st.write("✅ 경쟁사·규제·위협·시장 데이터 추출 완료")

        st.write("③ 5 Forces / PESTEL 분석 중...")
        analysis = analysis_agent.run(extracted)
        st.write("✅ 분석 완료")

        st.write("④ PPT 생성 중...")
        ppt_bytes = generate_ppt(analysis, query, date.today().strftime("%Y.%m.%d"))
        status.update(label="분석 완료", state="complete")

    st.divider()

    # 결과 탭
    tab1, tab2, tab3 = st.tabs(["Porter 5 Forces", "PESTEL", "Key Insights"])

    with tab1:
        ff = analysis["five_forces"]
        force_labels = {
            "competitive_rivalry": "경쟁강도",
            "supplier_power": "공급자 협상력",
            "buyer_power": "구매자 협상력",
            "threat_of_substitutes": "대체재 위협",
            "threat_of_new_entrants": "신규진입 위협",
        }
        for key, label in force_labels.items():
            force = ff[key]
            with st.container(border=True):
                col1, col2 = st.columns([1, 5])
                with col1:
                    st.markdown(f"**{label}**")
                    st.markdown(f"{'●' * force['score']}{'○' * (5 - force['score'])}  `{force['score']}/5`")
                with col2:
                    st.markdown(force["summary"])
                    for e in force.get("evidence", []):
                        st.caption(e)

    with tab2:
        pestel = analysis["pestel"]
        pestel_labels = {
            "political": "Political",
            "economic": "Economic",
            "social": "Social",
            "technological": "Technological",
            "environmental": "Environmental",
            "legal": "Legal",
        }
        cols = st.columns(3)
        for i, (key, label) in enumerate(pestel_labels.items()):
            item = pestel[key]
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{label}**  `{item.get('source_type', '')}`")
                    st.markdown(item["summary"])
                    for e in item.get("evidence", [])[:2]:
                        st.caption(e)

    with tab3:
        st.markdown("### 핵심 인사이트")
        for insight in analysis.get("key_insights", []):
            st.markdown(f"- {insight}")

        st.divider()
        st.markdown("### 데이터 한계")
        for limit in analysis.get("data_limitations", []):
            st.caption(f"⚠️ {limit}")

    st.divider()
    st.download_button(
        label="📊 PPT 다운로드",
        data=ppt_bytes,
        file_name=f"{query}_산업분석_{date.today().strftime('%Y%m%d')}.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
