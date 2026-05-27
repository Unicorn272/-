import json
import os
import anthropic
from dotenv import load_dotenv
from functions.db_manager import get_connection
from functions.dart_collector import find_corps_by_names, collect_by_corps

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _extract_json(text: str, open_bracket: str) -> str:
    """텍스트에서 첫 번째 JSON 객체/배열을 브래킷 매칭으로 추출"""
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


def _extract_keywords(query: str) -> dict:
    """사용자 입력에서 제품·적용분야 키워드 추출"""
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": f"""문장에서 제품명과 적용분야를 추출해 JSON 객체만 반환하세요. 설명 없이 JSON만.

문장: "{query}"
형식: {{"product": "제품명", "application": "적용분야"}}
없으면 빈 문자열. JSON만."""
        }]
    )
    try:
        raw = _extract_json(resp.content[0].text, "{")
        return json.loads(raw) if raw else {"product": "", "application": ""}
    except Exception:
        return {"product": "", "application": ""}


def _query_db(product: str, application: str) -> list[dict]:
    """segments 테이블에서 매칭 기업 조회"""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT f.corp_name, s.filing_id, s.revenue_share
            FROM segments s
            JOIN filings f ON f.id = s.filing_id
            WHERE (
                (? != '' AND (s.product LIKE ? OR s.industry_tags LIKE ?))
                OR
                (? != '' AND (s.application LIKE ? OR s.industry_tags LIKE ?))
            )
            AND (s.revenue_share >= 10 OR s.revenue_share IS NULL)
            ORDER BY s.revenue_share DESC NULLS LAST
        """, (
            product, f"%{product}%", f"%{product}%",
            application, f"%{application}%", f"%{application}%",
        )).fetchall()
    return [dict(r) for r in rows]


def _find_company_names(query: str) -> list[str]:
    """Claude에게 해당 산업/제품과 관련된 한국 상장 기업명 리스트 요청"""
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""다음 산업/제품 관련 한국 상장 기업명을 JSON 배열만 반환하세요. 설명 없이 배열만.

입력: "{query}"
예시 출력: ["삼성전기", "삼화콘덴서공업", "아모텍"]
최대 10개. JSON 배열만."""
        }]
    )
    try:
        raw = _extract_json(resp.content[0].text, "[")
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _filter_by_mention(product: str, results: list[dict]) -> list[dict]:
    """매출 비중 없는 기업은 filing 텍스트 내 키워드 언급 빈도 10회 이상만 포함"""
    filtered = []
    for r in results:
        if r["revenue_share"] is not None:
            filtered.append(r)
            continue
        with get_connection() as conn:
            row = conn.execute(
                "SELECT pdf_blob FROM filings WHERE id = ?", (r["filing_id"],)
            ).fetchone()
        if row and row["pdf_blob"]:
            from bs4 import BeautifulSoup
            text = BeautifulSoup(bytes(row["pdf_blob"]).decode("utf-8", errors="ignore"), features="xml").get_text()
            if text.count(product) >= 10:
                filtered.append(r)
    return filtered


def run(query: str) -> tuple[list[dict], str | None]:
    """사용자 쿼리 → (관련 기업 리스트, 경고 메시지 or None)
    경고: 해당 산업의 기업 중 2년 내 증권신고서가 하나도 없을 때.
    """
    keywords = _extract_keywords(query)
    product = keywords.get("product", "")
    application = keywords.get("application", "")

    results = _query_db(product, application)

    if not results:
        names = _find_company_names(query)
        if names:
            corps = find_corps_by_names(names)
            if corps:
                collect_by_corps(corps)
                results = _query_db(product, application)

    results = _filter_by_mention(product, results)

    warning = None
    if results:
        filing_ids = [r["filing_id"] for r in results]
        placeholders = ",".join("?" * len(filing_ids))
        with get_connection() as conn:
            has_sec = conn.execute(
                f"SELECT 1 FROM filings WHERE id IN ({placeholders}) AND report_type='securities' LIMIT 1",
                filing_ids,
            ).fetchone()
        if not has_sec:
            warning = "해당 산업의 기업 중 최근 2년 내 증권신고서가 없습니다. 사업보고서 기반으로 분석됩니다."

    return results, warning
