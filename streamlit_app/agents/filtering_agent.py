import json
import os
import re
import time
import requests
import anthropic
from dotenv import load_dotenv
from functions.db_manager import get_connection
from functions.dart_collector import find_corps_by_names, collect_by_corps, find_corps_by_industry, INDUSTRY_KEYWORD_MAP

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_etf_cache: dict = {"data": [], "ts": 0}


def _load_etf_list() -> list[dict]:
    """네이버 ETF 전체 목록 (24시간 메모리 캐시)."""
    if time.time() - _etf_cache["ts"] < 86400 and _etf_cache["data"]:
        return _etf_cache["data"]
    try:
        r = requests.get(
            "https://finance.naver.com/api/sise/etfItemList.nhn",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        items = r.json().get("result", {}).get("etfItemList", [])
        _etf_cache["data"] = items
        _etf_cache["ts"] = time.time()
        return items
    except Exception:
        return []


_STOPWORDS = {"산업", "분석", "해줘", "분석해줘", "관련", "섹터", "업종", "시장", "현황", "투자", "주식"}

_KEYWORD_EXPAND = {
    "제약": ["제약", "바이오", "헬스케어", "헬스", "의약", "생명"],
    "바이오": ["바이오", "제약", "헬스케어", "헬스", "의약", "생명"],
    "헬스케어": ["헬스케어", "헬스", "바이오", "제약", "의약"],
    "반도체": ["반도체", "메모리", "시스템반도체", "칩"],
    "배터리": ["배터리", "2차전지", "전지", "ESS"],
    "2차전지": ["2차전지", "배터리", "전지", "ESS"],
    "ESS": ["ESS", "2차전지", "배터리", "전지", "에너지저장"],
    "전기차": ["전기차", "EV", "친환경차", "2차전지"],
    "자동차": ["자동차", "모빌리티", "차량"],
    "조선": ["조선", "해운", "선박"],
    "방산": ["방산", "방위", "항공우주"],
    "로봇": ["로봇", "자동화", "휴머노이드"],
    "AI": ["AI", "인공지능", "테크", "소프트웨어"],
    "인공지능": ["인공지능", "AI", "테크"],
    "게임": ["게임", "엔터", "콘텐츠"],
    "엔터": ["엔터", "게임", "콘텐츠", "미디어"],
    "금융": ["금융", "은행", "보험", "증권"],
    "은행": ["은행", "금융"],
    "보험": ["보험", "금융"],
    "건설": ["건설", "부동산", "리츠"],
    "철강": ["철강", "소재", "금속"],
    "화학": ["화학", "소재", "석유화학"],
    "에너지": ["에너지", "태양광", "신재생", "수소"],
    "태양광": ["태양광", "신재생", "에너지", "수소"],
    "수소": ["수소", "신재생", "에너지"],
    "MLCC": ["MLCC", "전자부품", "반도체"],
    "디스플레이": ["디스플레이", "OLED", "LCD"],
    "통신": ["통신", "5G", "네트워크"],
}

def _filter_etfs(industry: str, all_etfs: list[dict]) -> list[dict]:
    """산업 키워드로 관련 ETF 필터링. 동의어 확장 + 미국/글로벌 ETF 제외."""
    base_words = [w for w in re.split(r'[\s\[\]()\-/]+', industry)
                  if len(w) >= 2 and w not in _STOPWORDS]
    # 동의어 확장
    expanded = set(base_words)
    for w in base_words:
        for key, synonyms in _KEYWORD_EXPAND.items():
            if w == key or w in synonyms:
                expanded.update(synonyms)
    words = list(expanded)

    exclude = ["미국", "글로벌", "US", "Global", "해외"]
    result = []
    for etf in all_etfs:
        name = etf.get("itemname", "")
        if any(ex in name for ex in exclude):
            continue
        if any(w in name for w in words):
            result.append(etf)
    return result


def _get_companies_and_purposes(industry: str, etfs: list[dict]) -> tuple[list[str], dict | None]:
    """ETF 목록 → 기업 목록 + 목적별 프리셋 동시 생성 (1 Claude call)."""
    etf_text = "\n".join(f"- {e['itemname']}" for e in etfs)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": f"""아래 한국 ETF들의 "{industry}" 산업 관련 주요 한국 상장 구성종목을 파악하고,
분석 목적별 추천 기업 세트를 함께 만들어주세요.

ETF 목록:
{etf_text}

규칙:
- 기업은 최대 15개, 미국 상장사 제외, 한국거래소 상장명 그대로
- **"{industry}"와 직접 관련된 사업을 하는 기업만 포함** (해당 산업이 핵심 매출원인 기업 우선)
- 해당 산업이 부수적 사업인 대기업(삼성전자, LG전자 등)은 가능한 제외
- purposes의 각 카테고리에는 해당 역할을 실제로 수행하는 기업만 배치
- purposes의 기업은 반드시 companies 목록에 있는 기업명만 사용
- 목적은 해당 산업에서 의미있는 3~4개 관점

JSON만 반환:
{{
  "companies": ["기업A", "기업B"],
  "purposes": {{
    "목적명1": ["기업A", "기업B"],
    "목적명2": ["기업C", "기업D"]
  }}
}}"""}],
    )
    raw = _extract_json(resp.content[0].text, "{")
    try:
        data = json.loads(raw) if raw else {}
        return data.get("companies", []), data.get("purposes") or None
    except Exception:
        return [], None


def _ask_key_companies_with_purposes(industry: str) -> tuple[list[str], dict | None]:
    """ETF 없을 때 폴백: web_search로 관련주 검색 → 기업 목록 + 목적 프리셋 한 번에 생성."""
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": f"""웹 검색으로 "{industry} 관련주", "{industry} 기업 종목"을 검색하세요.
검색 결과를 바탕으로 "{industry}" 산업의 한국 상장 기업 목록과 분석 목적별 추천 기업 세트를 만들어주세요.

규칙:
- 검색 결과에서 찾은 기업 우선, "{industry}"와 직접 관련된 기업만 포함
- 기업은 최대 15개, 한국거래소 상장명 그대로 (DART 등록 정식 기업명)
- purposes의 각 카테고리에는 해당 역할을 실제로 수행하는 기업만 배치
- purposes의 기업은 반드시 companies 목록에 있는 기업명만 사용
- 목적은 해당 산업에서 의미있는 3~4개 관점

JSON만 반환:
{{
  "companies": ["기업A", "기업B"],
  "purposes": {{
    "목적명1": ["기업A", "기업B"],
    "목적명2": ["기업C", "기업D"]
  }}
}}"""}],
    )
    raw = ""
    for block in resp.content:
        if hasattr(block, "text") and block.text.strip():
            raw = block.text
    raw = _extract_json(raw, "{")
    try:
        data = json.loads(raw) if raw else {}
        return data.get("companies", []), data.get("purposes") or None
    except Exception:
        return [], None


def _parse_query(query: str) -> dict:
    """Mode A(산업만) vs Mode B(산업+기업 직접 지정) 판별."""
    m = re.search(r'[\[\(]([^\]\)]+)[\]\)]', query)
    if m:
        corp_names = [n.strip() for n in m.group(1).split(',') if n.strip()]
        industry = query[:m.start()].strip()
        return {"mode": "B", "industry": industry, "corp_names": corp_names}
    return {"mode": "A", "industry": query}


def _extract_json(text: str, open_bracket: str) -> str:
    close_bracket = "]" if open_bracket == "[" else "}"
    start = text.find(open_bracket)
    if start == -1:
        return ""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == open_bracket:
            depth += 1
        elif text[i] == close_bracket:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def _query_db_by_names(corp_names: list[str]) -> list[dict]:
    """기업명 리스트로 DB에서 기업별 최신 신고서 1건씩 조회"""
    if not corp_names:
        return []
    placeholders = ",".join("?" * len(corp_names))
    sql = f"""
        SELECT f.corp_name, f.corp_code, f.id AS filing_id
        FROM filings f
        INNER JOIN (
            SELECT corp_name, MAX(filed_at) AS max_filed
            FROM filings
            WHERE corp_name IN ({placeholders})
            GROUP BY corp_name
        ) latest ON f.corp_name = latest.corp_name AND f.filed_at = latest.max_filed
    """
    with get_connection() as conn:
        rows = conn.execute(sql, corp_names).fetchall()
    return [{"corp_name": r["corp_name"], "corp_code": r["corp_code"],
             "filing_id": r["filing_id"], "revenue_share": None} for r in rows]


def _query_db_by_corp_codes(corp_codes: list[str]) -> list[dict]:
    """corp_code 리스트로 DB에서 기업별 최신 신고서 1건씩 조회"""
    if not corp_codes:
        return []
    placeholders = ",".join("?" * len(corp_codes))
    sql = f"""
        SELECT f.corp_name, f.corp_code, f.id AS filing_id
        FROM filings f
        INNER JOIN (
            SELECT corp_code, MAX(filed_at) AS max_filed
            FROM filings
            WHERE corp_code IN ({placeholders})
            GROUP BY corp_code
        ) latest ON f.corp_code = latest.corp_code AND f.filed_at = latest.max_filed
    """
    with get_connection() as conn:
        rows = conn.execute(sql, corp_codes).fetchall()
    return [{"corp_name": r["corp_name"], "corp_code": r["corp_code"],
             "filing_id": r["filing_id"], "revenue_share": None} for r in rows]


def _extract_industry_keywords(industry: str) -> list[str]:
    return [key for key in INDUSTRY_KEYWORD_MAP if key in industry]


def run(query: str) -> tuple[str, list[dict], str | None, list[str], dict | None]:
    """
    반환: (mode, companies, warning, etf_sources, purposes)
    purposes: {"목적명": ["기업A", ...]} — Mode A일 때만, 없으면 None
    """
    parsed = _parse_query(query)
    mode = parsed["mode"]
    industry = parsed["industry"]
    etf_sources: list[str] = []

    if mode == "B":
        corp_names = parsed["corp_names"]
        corps = find_corps_by_names(corp_names)
        if corps:
            collect_by_corps(corps)
        companies = _query_db_by_names(corp_names)
        return mode, companies, None, etf_sources, None

    # Mode A: ETF 우선 → 없으면 뉴스+Claude 폴백
    all_etfs = _load_etf_list()
    relevant_etfs = _filter_etfs(industry, all_etfs)

    if relevant_etfs:
        etf_sources = [e["itemname"] for e in relevant_etfs]
        all_names, purposes = _get_companies_and_purposes(industry, relevant_etfs)
    else:
        all_names, purposes = _ask_key_companies_with_purposes(industry)

    corp_map = {c["corp_name"]: c for c in find_corps_by_names(all_names)}

    unmatched = [n for n in all_names if n not in corp_map]
    if unmatched:
        for c in find_corps_by_names(unmatched):
            corp_map.setdefault(c["corp_name"], c)

    companies: list[dict] = []
    seen: set[str] = set()
    for name in all_names:
        c = corp_map.get(name)
        if c and c["corp_code"] not in seen:
            seen.add(c["corp_code"])
            companies.append({
                "corp_name": c["corp_name"], "corp_code": c["corp_code"],
                "stock_code": c.get("stock_code", ""), "filing_id": None, "revenue_share": None,
            })

    if not companies:
        return mode, [], None, etf_sources, None

    # purposes 유효성 검증: companies에 있는 기업명만 유지
    if purposes:
        matched = {c["corp_name"] for c in companies}
        purposes = {
            label: [n for n in corps if n in matched]
            for label, corps in purposes.items()
            if any(n in matched for n in corps)
        } or None

    return mode, companies, None, etf_sources, purposes
