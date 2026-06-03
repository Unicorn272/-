import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from agents import classification_agent
from styles import inject

st.set_page_config(page_title="기업분류검증", layout="wide")
inject()

with st.sidebar:
    st.markdown("### 기업분류검증")
    st.divider()
    if st.button("기록 초기화", use_container_width=True):
        st.session_state.history = []
        st.rerun()

st.title("기업-산업 분류 검증")
st.markdown("기업의 증권신고서·사업보고서 사업개요를 분석해서 해당 산업에 포함되는지 판정합니다.")
st.caption("기업명과 산업명을 입력하고 검증하기를 누르세요.")
st.divider()

left, right = st.columns([6, 2])

with left:
    col1, col2, col3 = st.columns([4, 4, 1])
    with col1:
        corp_name = st.text_input("기업명", placeholder="예: 삼성SDI")
    with col2:
        industry = st.text_input("산업명", placeholder="예: ESS 배터리")
    with col3:
        st.write("")
        st.write("")
        run_btn = st.button("검증하기", type="primary", disabled=not (corp_name and industry))

with right:
    st.markdown("""
**판정 기준**

✅ **포함** — 해당 산업이 주력 사업이거나 매출 비중이 유의미

⚠️ **부분포함** — 관련 사업이 있지만 주력은 아님

❌ **미포함** — 해당 산업과 무관

🚫 **오류** — 기업을 DART에서 찾지 못했거나 데이터 없음
""")

if run_btn:
    with st.spinner(f"'{corp_name}' 신고서 분석 중..."):
        result = classification_agent.run(corp_name, industry)

    if "history" not in st.session_state:
        st.session_state.history = []
    st.session_state.history.insert(0, {
        "corp_name": corp_name,
        "industry": industry,
        "result": result,
    })

# ── 결과 표시 ─────────────────────────────────────────────────────────────────
if "history" not in st.session_state or not st.session_state.history:
    st.stop()

for entry in st.session_state.history:
    r = entry["result"]
    verdict = r.get("verdict", "error")
    confidence = r.get("confidence")
    resolved = r.get("resolved_name", entry["corp_name"])
    filing_info = r.get("filing_info", {})

    verdict_emoji = {"포함": "✅", "미포함": "❌", "부분포함": "⚠️", "error": "🚫"}.get(verdict, "❓")
    conf_str = f" · 신뢰도: {confidence}" if confidence else ""
    reason = r.get("reason", "")

    v_class = verdict if verdict in ("포함", "미포함", "부분포함") else "error"
    safe_resolved = str(resolved).replace("<", "&lt;").replace(">", "&gt;")
    safe_industry = str(entry["industry"]).replace("<", "&lt;").replace(">", "&gt;")
    safe_verdict = str(verdict).replace("<", "&lt;").replace(">", "&gt;")
    safe_reason = str(reason).replace("<", "&lt;").replace(">", "&gt;")

    st.markdown(f"""<div class="verdict-card v-{v_class}">
        <div class="v-header">{verdict_emoji} {safe_resolved} — <strong>{safe_industry}</strong> 에 {safe_verdict}{conf_str}</div>
        <div class="v-reason">{safe_reason}</div>
    </div>""", unsafe_allow_html=True)

    # 근거 세그먼트
    matching = r.get("matching_segments", [])
    if matching:
        with st.expander("근거 세그먼트"):
            for seg in matching:
                st.markdown(f"- {seg}")

    # 전체 세그먼트 증거
    evidence = r.get("evidence", [])
    if evidence:
        with st.expander(f"신고서 전체 세그먼트 ({len(evidence)}개)"):
            rows = []
            for e in evidence:
                rows.append({
                    "사업부문": e.get("application") or "-",
                    "제품": e.get("product") or "-",
                    "매출비중(%)": f"{e['revenue_share']:.1f}" if e.get("revenue_share") else "-",
                })
            st.table(rows)

    # 출처
    if filing_info:
        filed_at = str(filing_info.get("filed_at", ""))[:7]
        report_type = "증권신고서" if filing_info.get("report_type") == "securities" else "사업보고서"
        st.caption(f"데이터 출처: {filed_at} {report_type}")

    st.divider()
