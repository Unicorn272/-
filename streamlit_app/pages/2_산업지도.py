import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
from functions.sector_mapper import get_sector_map
from styles import inject

st.set_page_config(page_title="산업지도", layout="wide")
inject()

with st.sidebar:
    st.markdown("### 산업지도")
    st.markdown("KRX 섹터 ETF 구성종목 기반")

st.title("한국 섹터 산업지도")
st.caption("KRX 섹터 ETF 구성종목 기반 · 출처: 네이버 금융")

with st.spinner("데이터 로딩 중..."):
    sector_map = get_sector_map()

total = sum(len(v) for v in sector_map.values())
if total == 0:
    st.error("ETF 구성종목을 불러오지 못했습니다. 네트워크 상태를 확인하고 새로고침을 눌러주세요.")
    st.stop()

# ── 트리맵 ────────────────────────────────────────────────────────────────────
SECTOR_COLORS = {
    "반도체":      "#1f77b4",
    "2차전지":     "#2ca02c",
    "자동차":      "#ff7f0e",
    "바이오":      "#d62728",
    "금융":        "#9467bd",
    "방산":        "#8c564b",
    "조선":        "#e377c2",
    "소프트웨어":  "#7f7f7f",
    "에너지/화학": "#bcbd22",
}

ROOT = "한국 산업지도"
labels   = [ROOT]
parents  = [""]
values   = [0]
colors   = ["#1B3A6B"]
customs  = [""]

for sector, companies in sector_map.items():
    if not companies:
        continue
    labels.append(sector)
    parents.append(ROOT)
    values.append(0)
    colors.append(SECTOR_COLORS.get(sector, "#aec7e8"))
    customs.append("")
    for c in companies:
        labels.append(c["name"])
        parents.append(sector)
        values.append(max(c["weight"], 0.5))
        colors.append(SECTOR_COLORS.get(sector, "#aec7e8"))
        customs.append(f"{c['weight']:.1f}%")

fig = go.Figure(go.Treemap(
    labels=labels,
    parents=parents,
    values=values,
    marker=dict(colors=colors, line=dict(width=1, color="#ffffff")),
    customdata=customs,
    hovertemplate="<b>%{label}</b><br>ETF 비중: %{customdata}<extra></extra>",
    textinfo="label",
    root_color="#1B3A6B",
    textfont=dict(size=13),
))
fig.update_layout(
    margin=dict(t=10, l=10, r=10, b=10),
    height=520,
)
st.plotly_chart(fig, use_container_width=True)

# ── 섹터별 기업 목록 ──────────────────────────────────────────────────────────
st.divider()
st.markdown("### 섹터별 기업 목록")
st.caption("분석하기 버튼을 누르면 산업분석 페이지로 이동합니다.")

cols = st.columns(3)
for i, (sector, companies) in enumerate(sector_map.items()):
    with cols[i % 3]:
        with st.expander(f"**{sector}** ({len(companies)}개)", expanded=False):
            if not companies:
                st.caption("데이터 없음")
                continue
            for j, c in enumerate(companies):
                c1, c2 = st.columns([3, 1])
                with c1:
                    weight_str = f" ({c['weight']:.1f}%)" if c["weight"] != 1.0 else ""
                    st.write(f"{c['name']}{weight_str}")
                with c2:
                    if st.button("분석", key=f"btn_{sector}_{j}"):
                        st.session_state["prefill_query"] = c["name"]
                        st.switch_page("pages/1_산업분석.py")
