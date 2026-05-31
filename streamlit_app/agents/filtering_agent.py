import json
import os
import re
import anthropic
from dotenv import load_dotenv
from functions.db_manager import get_connection
from functions.dart_collector import (
    find_corps_by_names, find_corps_by_industry,
    collect_by_corps, INDUSTRY_KEYWORD_MAP,
)

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


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


def _resolve_keyword(industry: str) -> list[str]:
    """산업 키워드를 INDUSTRY_KEYWORD_MAP 키로 매핑. 직접 매칭 없으면 Claude로 추론."""
    # 직접 매칭
    for key in INDUSTRY_KEYWORD_MAP:
        if key in industry or industry in key:
            return [key]

    # Claude로 가장 가까운 키 추론
    keys = list(INDUSTRY_KEYWORD_MAP.keys())
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=64,
        messages=[{
            "role": "user",
            "content": f"""다음 산업 키워드 목록에서 "{industry}"와 가장 관련 있는 항목들을 골라 JSON 배열로 반환하세요.
없으면 빈 배열.
목록: {keys}
JSON 배열만, 설명 없이."""
        }]
    )
    try:
        raw = _extract_json(resp.content[0].text, "[")
        matched = json.loads(raw) if raw else []
        return [k for k in matched if k in INDUSTRY_KEYWORD_MAP]
    except Exception:
        return []


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


def group_by_subsector(companies: list[dict], query: str) -> dict[str, list[str]]:
    """기업 목록 → Claude로 밸류체인 기준 그룹핑"""
    if not companies:
        return {}

    corp_names = [c["corp_name"] for c in companies]
    name_list = "\n".join(f"- {n}" for n in corp_names)

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""산업: "{query}"

다음 기업들을 밸류체인 위치 또는 사업 특성 기준으로 2~4개 그룹으로 나누세요.
그룹명은 간결하게(예: "배터리셀", "양극재", "ESS 통합솔루션").
JSON만 반환. 형식: {{"그룹명": ["기업A", "기업B"]}}

기업 목록:
{name_list}"""
        }]
    )

    valid_names = {c["corp_name"] for c in companies}
    try:
        raw = _extract_json(resp.content[0].text, "{")
        result: dict[str, list[str]] = json.loads(raw) if raw else {}
        validated: dict[str, list[str]] = {}
        for label, names in result.items():
            valid = [n for n in names if n in valid_names]
            if valid:
                validated[label] = valid
        classified = {n for ns in validated.values() for n in ns}
        leftover = [c["corp_name"] for c in companies if c["corp_name"] not in classified]
        if leftover:
            validated["기타"] = leftover
        return validated
    except Exception:
        return {"전체": corp_names}


def run(query: str) -> tuple[str, list[dict], dict | None, str | None]:
    """
    반환: (mode, companies, subsectors, warning)
    """
    parsed = _parse_query(query)
    mode = parsed["mode"]
    industry = parsed["industry"]

    if mode == "B":
        corp_names = parsed["corp_names"]
        corps = find_corps_by_names(corp_names)
        if corps:
            collect_by_corps(corps)
        companies = _query_db_by_names(corp_names)
        subsectors = None

    else:
        # Mode A: 업종코드로 기업 조회
        keywords = _resolve_keyword(industry)
        corps = []
        for kw in keywords:
            corps.extend(find_corps_by_industry(kw))
        # 중복 제거
        seen = set()
        corps = [c for c in corps if not (c["corp_code"] in seen or seen.add(c["corp_code"]))]

        if corps:
            collect_by_corps(corps)

        corp_codes = [c["corp_code"] for c in corps]
        companies = _query_db_by_corp_codes(corp_codes)
        subsectors = group_by_subsector(companies, industry) if companies else {}

    warning = None
    if companies:
        filing_ids = [c["filing_id"] for c in companies]
        placeholders = ",".join("?" * len(filing_ids))
        with get_connection() as conn:
            has_sec = conn.execute(
                f"SELECT 1 FROM filings WHERE id IN ({placeholders}) AND report_type='securities' LIMIT 1",
                filing_ids,
            ).fetchone()
        if not has_sec:
            warning = "해당 산업의 기업 중 최근 2년 내 증권신고서가 없습니다. 사업보고서 기반으로 분석됩니다."

    return mode, companies, subsectors, warning
