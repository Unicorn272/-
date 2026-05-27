import json
import os
import anthropic
from dotenv import load_dotenv
from functions.db_manager import get_connection
from functions.pdf_parser import extract_business_risk
from functions.news_searcher import search_news

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

EMPTY_RESULT = {
    "competitors": [],
    "regulations": [],
    "threats": [],
    "market_data": [],
}


def _extract_from_text(text: str) -> dict:
    """투자위험요소 텍스트 → Claude API로 JSON 추출 (1회 호출)"""
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": f"""다음 텍스트에서 아래 항목을 JSON으로 추출하세요.
수치는 반드시 원문 그대로, 출처 기관명과 함께 기재하세요.

{{
  "competitors": [{{"name": "", "market_share": "", "country": "", "strength": ""}}],
  "regulations": [{{"name": "", "effective_date": "", "impact": ""}}],
  "threats": [{{"factor": "", "description": "", "data": ""}}],
  "market_data": [{{"metric": "", "value": "", "source": "", "year": ""}}]
}}

텍스트: {text[:150000]}"""
        }]
    )
    try:
        raw = resp.content[0].text
        depth, start = 0, -1
        for i, ch in enumerate(raw):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    return json.loads(raw[start:i + 1])
    except Exception:
        pass
    return EMPTY_RESULT.copy()


def _merge_results(results: list[dict]) -> dict:
    """
    복수 신고서 결과 병합.
    market_data 수치 충돌 시 범위로 표시 ("109억~250억달러").
    """
    merged = {"competitors": [], "regulations": [], "threats": [], "market_data": []}

    seen_competitors = {}
    for r in results:
        for c in r.get("competitors", []):
            key = c.get("name", "")
            if key not in seen_competitors:
                seen_competitors[key] = c
        for reg in r.get("regulations", []):
            if reg not in merged["regulations"]:
                merged["regulations"].append(reg)
        for t in r.get("threats", []):
            if t not in merged["threats"]:
                merged["threats"].append(t)

    merged["competitors"] = list(seen_competitors.values())

    # market_data: 같은 metric이면 값 범위로 합치기
    metric_values: dict[str, list] = {}
    metric_meta: dict[str, dict] = {}
    for r in results:
        for m in r.get("market_data", []):
            key = m.get("metric", "")
            metric_values.setdefault(key, []).append(m.get("value", ""))
            metric_meta[key] = m

    for metric, values in metric_values.items():
        unique = list(dict.fromkeys(values))
        entry = metric_meta[metric].copy()
        entry["value"] = unique[0] if len(unique) == 1 else f"{unique[0]}~{unique[-1]}"
        merged["market_data"].append(entry)

    return merged


def _needs_news_supplement(data: dict) -> list[str]:
    """부족한 항목 감지 → 뉴스 보완 대상 PESTEL 카테고리 반환"""
    missing = []
    if len(data.get("competitors", [])) < 2:
        missing.append("Political")
    if not data.get("market_data"):
        missing.append("Economic")
    missing.append("Social")  # 신고서에서 항상 약한 항목
    return missing


def run(companies: list[dict], query: str) -> dict:
    """
    필터링된 기업 리스트 → 추출 결과 반환
    반환: {merged_data, news_supplements}
    """
    raw_results = []
    processed_filing_ids = []  # 실제 추출된 securities filing_id만 추적

    for company in companies:
        filing_id = company["filing_id"]
        with get_connection() as conn:
            row = conn.execute(
                "SELECT pdf_blob, report_type FROM filings WHERE id = ?", (filing_id,)
            ).fetchone()

        if not row or not row["pdf_blob"]:
            continue
        if row["report_type"] != "securities":
            continue  # 투자위험요소는 증권신고서에만 있음

        pdf_bytes = bytes(row["pdf_blob"])
        section_text = extract_business_risk(pdf_bytes)
        if not section_text.strip():
            continue

        extracted = _extract_from_text(section_text)
        raw_results.append(extracted)
        processed_filing_ids.append(filing_id)

    if not raw_results:
        merged = EMPTY_RESULT.copy()
    else:
        merged = _merge_results(raw_results)

    # 뉴스 보완
    news_supplements = {}
    for category in _needs_news_supplement(merged):
        news_supplements[category] = search_news(query, category)

    # DB 저장 — 실제 추출된 securities filing_id 기준으로 저장
    for fid in processed_filing_ids:
        with get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO analysis_results
                   (filing_id, competitors, regulations, threats, market_data, news_supplements)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    fid,
                    json.dumps(merged["competitors"], ensure_ascii=False),
                    json.dumps(merged["regulations"], ensure_ascii=False),
                    json.dumps(merged["threats"], ensure_ascii=False),
                    json.dumps(merged["market_data"], ensure_ascii=False),
                    json.dumps(news_supplements, ensure_ascii=False),
                )
            )

    return {"data": merged, "news_supplements": news_supplements}
