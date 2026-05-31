import json
import os
import re
import anthropic
from dotenv import load_dotenv
from functions.db_manager import get_connection
from functions.dart_collector import find_corps_by_names, collect_by_corps

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _parse_query(query: str) -> dict:
    """Mode A(산업만) vs Mode B(산업+기업 직접 지정) 판별.
    Mode B 형식: "ESS [삼성SDI, LG에너지솔루션]" 또는 "ESS (삼성SDI, LG에너지솔루션)"
    """
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


def _parse_name_list(text: str) -> list[str]:
    raw = _extract_json(text, "[")
    items = json.loads(raw) if raw else []
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            name = item.get("company") or item.get("name") or item.get("corp_name") or ""
            if name:
                result.append(name)
    return result


def _find_companies_by_web(industry: str) -> list[str]:
    """Claude Sonnet + web_search로 국내 상장기업 발견 (뉴스 우선 + 지식 보완)"""
    # 1순위: 최근 뉴스 기반
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": f"""웹 검색으로 "{industry}" 산업 관련 최근 뉴스를 찾아주세요.
뉴스에 등장하는 한국 KOSPI·KOSDAQ 상장 기업명만 추출해 JSON 문자열 배열로 반환하세요.
최근에 자주 언급된 기업을 앞에 두세요.
예: ["기업A", "기업B"]
JSON 배열만, 설명 없이."""
        }]
    )
    news_names: list[str] = []
    for block in resp.content:
        if hasattr(block, "text") and block.text.strip():
            try:
                news_names = _parse_name_list(block.text)
            except Exception:
                pass

    # 2순위: Claude 지식 기반 보완
    resp2 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f""""{industry}" 산업에 직접 종사하는 한국 KOSPI·KOSDAQ 상장 기업을 최대한 많이 찾아주세요.
대기업부터 중소형까지 포함. 최대 20개. JSON 문자열 배열만.
예: ["기업A", "기업B"]"""
        }]
    )
    try:
        knowledge_names = _parse_name_list(resp2.content[0].text)
    except Exception:
        knowledge_names = []

    seen = set(news_names)
    combined = list(news_names)
    for name in knowledge_names:
        if name not in seen:
            seen.add(name)
            combined.append(name)
    return combined


def _query_db_by_names(corp_names: list[str]) -> list[dict]:
    """기업명 리스트로 filings 테이블에서 기업별 최신 신고서 1건씩 조회"""
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


def group_by_subsector(companies: list[dict], query: str) -> dict[str, list[str]]:
    """기업별 세그먼트 데이터 → Claude Sonnet으로 동적 세부 분야 그룹핑"""
    if not companies:
        return {}

    filing_ids = list({c["filing_id"] for c in companies})
    placeholders = ",".join("?" * len(filing_ids))

    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT f.corp_name, s.product, s.application, s.revenue_share
            FROM segments s JOIN filings f ON f.id = s.filing_id
            WHERE s.filing_id IN ({placeholders})
            ORDER BY s.revenue_share DESC NULLS LAST
        """, filing_ids).fetchall()

    corp_segs: dict[str, list[str]] = {}
    for r in rows:
        name = r["corp_name"]
        seg = f"{r['product'] or ''} / {r['application'] or ''}".strip(" /")
        corp_segs.setdefault(name, [])
        if len(corp_segs[name]) < 2 and seg:
            corp_segs[name].append(seg)

    corp_summary = "\n".join(
        f"- {name}: {', '.join(segs)}" for name, segs in corp_segs.items() if segs
    )
    # 세그먼트 없는 기업도 포함
    all_names = [c["corp_name"] for c in companies]
    no_seg = [n for n in all_names if n not in corp_segs]
    if no_seg:
        corp_summary += "\n" + "\n".join(f"- {n}: (세그먼트 정보 없음)" for n in no_seg)

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
{corp_summary}"""
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
        leftover = list(dict.fromkeys(c["corp_name"] for c in companies if c["corp_name"] not in classified))
        if leftover:
            validated["기타"] = leftover
        return validated
    except Exception:
        names = list(dict.fromkeys(c["corp_name"] for c in companies))
        return {"전체": names}


def run(query: str) -> tuple[str, list[dict], dict | None, str | None]:
    """
    반환: (mode, companies, subsectors, warning)
    - mode: "A"(산업만) | "B"(산업+기업직접)
    - companies: [{corp_name, corp_code, filing_id, revenue_share}]
    - subsectors: {분야명: [기업명, ...]} (Mode A만, Mode B는 None)
    - warning: 증권신고서 없을 때 경고 메시지
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
        # Mode A: 웹서치로 기업 발견
        names = _find_companies_by_web(industry)
        if names:
            corps = find_corps_by_names(names)
            if corps:
                collect_by_corps(corps)
        companies = _query_db_by_names(names) if names else []
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
