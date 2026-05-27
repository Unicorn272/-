# CLAUDE.md

# 증권신고서 기반 산업분석 자동화 앱 — 프로젝트 스펙

## 개요

DART 전자공시시스템의 증권신고서·사업보고서를 자동 수집·파싱하여
사용자가 원하는 산업에 대한 Porter 5 Forces + PESTEL 분석을 자동으로 수행하고
PPT로 출력해주는 Streamlit 앱.

---

## 기술 스택

- **Frontend**: Streamlit
- **Backend**: Python 3.11+
- **DB**: SQLite (프로토타입) → PostgreSQL (배포 시)
- **AI**: Claude API (claude-sonnet-4-20250514)
- **PDF 파싱**: pdftotext (poppler-utils), pdfplumber
- **PPT 생성**: python-pptx
- **스케줄러**: APScheduler
- **뉴스 검색**: 웹 검색 API (Claude web_search tool)
- **환경변수**: python-dotenv

---

## 디렉토리 구조

```
streamlit_app/
├── app.py                        # 메인 진입점
├── pages/
│   ├── 1_산업분석.py              # 사용자 요청 → PPT 생성
│   └── 2_DB관리.py               # 관리자용 DB 현황 모니터링
├── agents/
│   ├── filtering_agent.py        # Agent 1: 기업 필터링
│   ├── extraction_agent.py       # Agent 2: 데이터 추출
│   └── analysis_agent.py         # Agent 3: 5Forces + PESTEL 분석
├── functions/
│   ├── dart_collector.py         # DART API 수집
│   ├── pdf_parser.py             # PDF 파싱 + 섹션 추출
│   ├── news_searcher.py          # 뉴스 검색 (보완용)
│   ├── db_manager.py             # DB CRUD
│   └── ppt_generator.py          # PPT 생성
├── scheduler/
│   └── weekly_update.py          # 주간 자동 업데이트
├── db/
│   └── database.db               # SQLite DB
├── requirements.txt
└── .env                          # API 키 관리
```

---

## DB 스키마

```sql
-- 신고서 원본 정보
CREATE TABLE filings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    corp_name TEXT NOT NULL,          -- 회사명
    corp_code TEXT NOT NULL,          -- DART 고유번호
    stock_code TEXT,                  -- 종목코드
    report_type TEXT,                 -- 'securities' | 'annual'
    filed_at DATE NOT NULL,           -- 제출일자
    doc_url TEXT,                     -- PDF URL
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 사업부 단위 분류 (필터링 핵심)
CREATE TABLE segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id INTEGER REFERENCES filings(id),
    application TEXT,                 -- 적용 분야 (전기차, 핸드폰, AI서버 등)
    product TEXT,                     -- 제품명 (MLCC, 안테나, BLDC 등)
    revenue_share REAL,               -- 매출 비중 (%)
    industry_tags TEXT,               -- JSON 배열 ["MLCC", "전기차"]
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 추출된 분석 데이터
CREATE TABLE analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id INTEGER REFERENCES filings(id),
    competitors TEXT,                 -- JSON: [{name, share, country, strength}]
    regulations TEXT,                 -- JSON: [{name, effective_date, impact}]
    threats TEXT,                     -- JSON: [{factor, description, severity}]
    market_data TEXT,                 -- JSON: [{metric, value, source, year}]
    news_supplements TEXT,            -- JSON: 뉴스로 보완한 항목
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Agent 설계

### Agent 1 — 필터링 Agent

**역할**: 사용자 입력에서 산업 키워드 추출 → DB 조회 → 관련 기업 선별

**입력**: 사용자 자연어 입력 ("전기차 MLCC 분석해줘")

**처리 로직**:
1. 입력에서 제품(MLCC)과 적용분야(전기차) 추출
2. DB `segments` 테이블에서 매칭 기업 조회
3. DB에 없으면 → DART API 실시간 수집 트리거
4. 매출 비중 기준 정렬 (비중 높은 순)

**출력**: `[{corp_name, filing_id, revenue_share}]`

**판단 기준**:
- 해당 제품·분야 매출 비중 10% 이상인 기업 포함
- 비중 정보 없으면 키워드 언급 빈도 10회 이상

---

### Agent 2 — 추출 Agent

**역할**: 투자위험요소 파싱 → 경쟁사·규제·위협·수치 추출 → 뉴스 보완

**입력**: 필터링된 기업 리스트 + filing_id

**처리 로직**:
1. 신고서 PDF에서 투자위험요소 섹션만 추출 (목차 기반 페이지 범위)
2. Claude API 호출 (1회) — 아래 항목 JSON으로 동시 추출:
   - 경쟁사명, 점유율, 국가, 강점
   - 규제 항목, 시행 시기, 영향
   - 위협 요인, 근거 수치
   - 시장 규모 수치 + 출처 기관명
3. 수치 범위 처리: 복수 신고서에서 같은 항목 수치가 다를 경우 중앙값·범위 표시
4. 부족 항목 감지 → 뉴스 검색 tool 호출 (정성 맥락만, 수치는 제외)
5. DB 저장

**수치 처리 원칙**:
- 신고서 수치: 1차 자료로 사용, 출처 기관명 병기 필수
- 뉴스 수치: 사용 금지, 정성적 맥락만 활용
- 복수 수치 충돌 시: 범위로 표시 ("109억~250억달러")

**Claude 프롬프트 구조**:
```
다음 텍스트에서 아래 항목을 JSON으로 추출하세요.
수치는 반드시 원문 그대로, 출처 기관명과 함께 기재하세요.

{
  "competitors": [{"name": "", "market_share": "", "country": "", "strength": ""}],
  "regulations": [{"name": "", "effective_date": "", "impact": ""}],
  "threats": [{"factor": "", "description": "", "data": ""}],
  "market_data": [{"metric": "", "value": "", "source": "", "year": ""}]
}

텍스트: {section_text}
```

---

### Agent 3 — 분석 Agent

**역할**: 추출 데이터 → Porter 5 Forces + PESTEL 작성

**입력**: Agent 2 출력 JSON + 뉴스 보완 데이터

**출력 구조**:

```json
{
  "five_forces": {
    "competitive_rivalry": {"score": 4, "summary": "", "evidence": ["출처: A사 신고서 2025.03"]},
    "supplier_power": {"score": 3, "summary": "", "evidence": []},
    "buyer_power": {"score": 3, "summary": "", "evidence": []},
    "threat_of_substitutes": {"score": 2, "summary": "", "evidence": []},
    "threat_of_new_entrants": {"score": 3, "summary": "", "evidence": []}
  },
  "pestel": {
    "political": {"summary": "", "evidence": [], "source_type": "신고서|뉴스"},
    "economic": {"summary": "", "evidence": [], "source_type": "신고서|뉴스"},
    "social": {"summary": "", "evidence": [], "source_type": "뉴스"},
    "technological": {"summary": "", "evidence": [], "source_type": "신고서|뉴스"},
    "environmental": {"summary": "", "evidence": [], "source_type": "신고서|뉴스"},
    "legal": {"summary": "", "evidence": [], "source_type": "신고서|뉴스"}
  },
  "key_insights": ["인사이트 1", "인사이트 2"],
  "data_limitations": ["Social 항목은 뉴스 기반으로 신뢰도 낮음"]
}
```

**중요**: 항목마다 출처를 신고서/뉴스로 구분 표시. 데이터 한계도 명시.

---

## 파싱 전략 (토큰 최적화 핵심)

### 2단계 파싱

```
1단계 — 필터링용 (사업의 내용만)
목차 파싱 → "사업의 내용" 페이지 범위 확인
→ 해당 섹션만 추출 (평균 15~20p)
→ 제품·적용분야·매출비중 추출
→ DB 저장

2단계 — 분석용 (투자위험요소만)
목차 파싱 → "투자위험요소" 페이지 범위 확인
→ 해당 섹션만 추출 (평균 30~50p)
→ 경쟁사·규제·위협·수치 추출
→ DB 저장
```

### 목차 파싱 실패 시 폴백

```python
# 목차 파싱 실패 시 헤더 키워드로 청킹
SECTION_KEYWORDS = {
    "사업의 내용": ["II. 사업의 내용", "사업의 개요"],
    "투자위험요소": ["III. 투자위험요소", "Ⅲ. 투자위험요소"]
}
```

---

## DART 수집 전략

```python
# DART Open API 엔드포인트
BASE_URL = "https://opendart.fss.or.kr/api"

# 신고서 목록 조회
GET /list.json
  ?corp_cls=Y|K        # 유가증권|코스닥
  &pblntf_ty=A         # 증권신고서
  &bgn_de=20240101     # 2년치
  &end_de=20260526
  &page_count=100

# 사업보고서도 병행 수집 (모수 확대)
  &pblntf_ty=A001      # 사업보고서
```

**수집 대상 업종 코드 (표준산업분류)**:
- C261: 반도체 제조업
- C262: 전자부품 제조업
- C291: 자동차 제조업 (전장 포함)

---

## 뉴스 검색 원칙

**허용 소스**: 연합뉴스, 한국경제, 매일경제, 전자신문, 디일렉, Reuters, Bloomberg

**활용 범위**:
- O 정성적 맥락 보완 (트렌드, 정책 방향)
- X 수치 인용 금지

**보완 대상 PESTEL 항목**: Social, Political (신고서에서 약한 항목)

---

## Streamlit UI 흐름

```python
# pages/1_산업분석.py 핵심 구조

st.title("산업분석 자동화")
query = st.text_input("분석할 산업을 입력하세요", placeholder="예: 전기차 MLCC")

if st.button("분석 시작"):
    with st.status("분석 중...", expanded=True) as status:

        st.write("관련 기업 조회 중...")
        companies = filtering_agent.run(query)
        st.write(f"✅ {len(companies)}개 기업 선별: {[c['corp_name'] for c in companies]}")

        st.write("투자위험요소 추출 중...")
        extracted = extraction_agent.run(companies)
        st.write("✅ 경쟁사·규제·위협 추출 완료")

        st.write("5 Forces / PESTEL 분석 중...")
        analysis = analysis_agent.run(extracted)
        st.write("✅ 분석 완료")

        st.write("PPT 생성 중...")
        ppt_path = generate_ppt(analysis, query)
        status.update(label="완료!", state="complete")

    with open(ppt_path, "rb") as f:
        st.download_button(
            label="📊 PPT 다운로드",
            data=f,
            file_name=f"{query}_산업분석.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
```

---

## PPT 슬라이드 구성

```
Slide 1: 표지 (산업명, 분석 기준일, 분석 기업 수)
Slide 2: 분석 개요 (사용 신고서 목록, 데이터 한계 명시)
Slide 3: Porter 5 Forces 다이어그램 (점수 포함)
Slide 4: 5 Forces 상세 — 경쟁 강도
Slide 5: 5 Forces 상세 — 공급자·구매자 교섭력
Slide 6: 5 Forces 상세 — 신규진입·대체재 위협
Slide 7: PESTEL 요약 매트릭스
Slide 8~13: PESTEL 항목별 상세 (출처 표시)
Slide 14: 핵심 인사이트 (3~5개)
Slide 15: 데이터 출처 및 한계
```

---

## 개발 순서

```
1단계 (기반)
├── .env 설정 (DART_API_KEY, ANTHROPIC_API_KEY)
├── dart_collector.py — DART API 연동
├── pdf_parser.py — 목차 파싱 + 섹션 추출
└── db_manager.py — SQLite 스키마 생성 + CRUD

2단계 (Agent)
├── filtering_agent.py
├── extraction_agent.py
└── analysis_agent.py

3단계 (출력)
├── news_searcher.py
└── ppt_generator.py

4단계 (Streamlit)
├── app.py
├── pages/1_산업분석.py
└── pages/2_DB관리.py

5단계 (운영)
└── scheduler/weekly_update.py
```

---

## 개발 명령어

```bash
# 의존성 설치
pip install -r requirements.txt

# 앱 실행
streamlit run streamlit_app/app.py

# DB 초기화 (최초 1회)
python functions/db_manager.py --init

# 사전 데이터 수집 (최초 1회)
python scheduler/weekly_update.py --full

# 주간 업데이트 (신규 신고서만)
python scheduler/weekly_update.py --incremental

# 환경변수 설정
cp .env.example .env
```

---

## 환경변수 (.env)

```
DART_API_KEY=your_dart_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
DB_PATH=./db/database.db
NEWS_SEARCH_ENABLED=true
MAX_COMPANIES_PER_QUERY=15
FILING_LOOKBACK_YEARS=2
```

---

## 핵심 설계 원칙

1. **Agent는 3개만** — 판단이 필요한 것만 Agent, 나머지는 함수
2. **2단계 파싱** — 사업의 내용(필터링) → 투자위험요소(분석), 토큰 절약
3. **수치 출처 구분** — 신고서 vs 뉴스 항상 명시
4. **캐싱 우선** — DB에 있으면 재파싱 없이 바로 사용
5. **데이터 한계 명시** — Social 항목 약함 등 결과물에 투명하게 표시