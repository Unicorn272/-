import streamlit as st

_CSS = """
<style>
/* ── 사이드바 ──────────────────────────────────────────── */
[data-testid="stSidebar"] { background: #1B3A6B !important; box-shadow: 2px 0 8px rgba(0,0,0,0.12); }
[data-testid="stSidebar"] * { color: #FFFFFF !important; }
[data-testid="stSidebarNav"] a { border-radius: 6px !important; margin: 1px 6px !important; transition: background 0.15s !important; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: rgba(255,255,255,0.2) !important; font-weight: 700 !important; }
[data-testid="stSidebarNav"] a:hover { background: rgba(255,255,255,0.12) !important; }

/* ── 레이아웃 ──────────────────────────────────────────── */
.main .block-container { padding-top: 1.5rem !important; max-width: 1100px !important; }

/* ── 타이포그래피 ──────────────────────────────────────── */
h1 { color: #1B3A6B !important; font-weight: 800 !important; border-left: 4px solid #1B3A6B; padding-left: 12px !important; margin-bottom: 4px !important; }
h2 { color: #1B3A6B !important; font-weight: 700 !important; }
h3, h4 { color: #1e293b !important; font-weight: 600 !important; }

/* ── 버튼 ──────────────────────────────────────────────── */
.stButton > button { border-radius: 6px !important; font-weight: 600 !important; transition: all 0.15s !important; }
.stButton > button[kind="primary"] { background: #1B3A6B !important; border: none !important; color: white !important; }
.stButton > button[kind="primary"]:hover:not(:disabled) { background: #142d54 !important; box-shadow: 0 2px 10px rgba(27,58,107,0.35) !important; transform: translateY(-1px) !important; }
.stButton > button:not([kind="primary"]) { border: 1.5px solid #D1D5DB !important; color: #374151 !important; }

/* ── 입력 ──────────────────────────────────────────────── */
.stTextInput input { border-radius: 6px !important; border: 1.5px solid #D1D5DB !important; }
.stTextInput input:focus { border-color: #1B3A6B !important; box-shadow: 0 0 0 3px rgba(27,58,107,0.1) !important; }

/* ── 탭 ────────────────────────────────────────────────── */
button[data-baseweb="tab"] { font-weight: 600 !important; }
button[data-baseweb="tab"][aria-selected="true"] { color: #1B3A6B !important; }
[data-baseweb="tab-highlight"] { background: #1B3A6B !important; }

/* ── 다운로드 버튼 ─────────────────────────────────────── */
[data-testid="stDownloadButton"] > button { background: #166534 !important; color: white !important; border: none !important; border-radius: 6px !important; font-weight: 600 !important; }
[data-testid="stDownloadButton"] > button:hover { background: #14532d !important; box-shadow: 0 2px 8px rgba(22,101,52,0.3) !important; }

/* ── Divider ────────────────────────────────────────────── */
hr { border-color: #E5E7EB !important; }

/* ── 랜딩 카드 ─────────────────────────────────────────── */
.feature-card {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-top: 3px solid #1B3A6B;
    border-radius: 8px;
    padding: 22px 24px 18px;
    min-height: 160px;
    margin-bottom: 8px;
}
.feature-icon { font-size: 1.8rem; margin-bottom: 10px; }
.feature-title { font-size: 1rem; font-weight: 700; color: #1B3A6B; margin-bottom: 6px; }
.feature-desc { font-size: 0.82rem; color: #64748B; line-height: 1.65; }

/* ── 스텝 바 ───────────────────────────────────────────── */
.step-bar { display: flex; align-items: center; padding: 8px 0 20px 0; }
.s-item { display: flex; align-items: center; gap: 7px; font-size: 0.82rem; font-weight: 600; color: #9CA3AF; }
.s-item.active { color: #1B3A6B; }
.s-item.done { color: #16a34a; }
.s-circle {
    width: 26px; height: 26px; border-radius: 50%;
    border: 2px solid #D1D5DB;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.75rem; font-weight: 700;
    background: white; color: #9CA3AF; flex-shrink: 0;
}
.s-item.active .s-circle { border-color: #1B3A6B; background: #1B3A6B; color: white; }
.s-item.done  .s-circle { border-color: #16a34a;  background: #16a34a;  color: white; }
.s-line { height: 1px; width: 36px; background: #E5E7EB; margin: 0 8px; }

/* ── 덱 구성 슬라이드 카드 ─────────────────────────────── */
.section-badge {
    display: inline-block;
    background: #1B3A6B; color: white !important;
    font-size: 0.68rem; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase;
    padding: 3px 10px; border-radius: 4px; margin-bottom: 6px;
}
.section-heading { font-size: 1.05rem; font-weight: 700; color: #1e293b; margin: 2px 0 14px 0; }
.slide-card {
    background: #FAFBFD;
    border: 1px solid #E2E8F0;
    border-left: 3px solid #1B3A6B;
    border-radius: 6px;
    padding: 14px 16px;
    margin-bottom: 10px;
    height: calc(100% - 10px);
}
.slide-no { font-size: 0.65rem; font-weight: 700; color: #1B3A6B; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 5px; }
.slide-title { font-size: 0.9rem; font-weight: 700; color: #1e293b; margin-bottom: 6px; line-height: 1.35; }
.slide-desc { font-size: 0.79rem; color: #64748B; line-height: 1.55; }
.key-message {
    background: #EEF2FF; border-left: 3px solid #4F46E5;
    border-radius: 0 6px 6px 0; padding: 10px 16px; margin-top: 10px;
    font-size: 0.87rem; color: #3730A3; font-weight: 500;
}

/* ── 기업분류 판정 카드 ────────────────────────────────── */
.verdict-card { border-radius: 8px; padding: 16px 20px; margin-bottom: 8px; border: 1px solid; }
.v-포함     { background: #F0FDF4; border-color: #86EFAC; }
.v-미포함   { background: #FEF2F2; border-color: #FECACA; }
.v-부분포함 { background: #FFFBEB; border-color: #FDE68A; }
.v-error    { background: #F9FAFB; border-color: #E5E7EB; }
.v-header { font-size: 1rem; font-weight: 700; color: #1e293b; margin-bottom: 5px; }
.v-reason { font-size: 0.85rem; color: #374151; line-height: 1.6; }
</style>
"""


def inject():
    st.markdown(_CSS, unsafe_allow_html=True)


def step_bar(step: str) -> str:
    idx = {"input": 0, "select": 1, "analyze": 2, "done": 2}
    cur = idx.get(step, 0)
    labels = [("1", "입력"), ("2", "기업 선택"), ("3", "분석")]
    html = '<div class="step-bar">'
    for i, (n, lbl) in enumerate(labels):
        cls = "done" if i < cur else ("active" if i == cur else "")
        icon = "✓" if i < cur else n
        html += f'<div class="s-item {cls}"><div class="s-circle">{icon}</div>{lbl}</div>'
        if i < 2:
            html += '<div class="s-line"></div>'
    html += "</div>"
    return html
