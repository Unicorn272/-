import json
import os
import re
import anthropic
from dotenv import load_dotenv
from functions.dart_collector import find_corps_by_names, collect_by_corps
from functions.db_manager import get_connection

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _get_segments(corp_code: str) -> list:
    with get_connection() as conn:
        # 보고서 종류 무관 가장 최근 filing 1개의 세그먼트만 조회
        row = conn.execute(
            "SELECT id FROM filings WHERE corp_code = ? ORDER BY filed_at DESC LIMIT 1",
            (corp_code,),
        ).fetchone()
        if not row:
            return []
        rows = conn.execute(
            """
            SELECT s.product, s.application, s.revenue_share, f.filed_at, f.report_type
            FROM segments s
            JOIN filings f ON s.filing_id = f.id
            WHERE s.filing_id = ?
            """,
            (row["id"],),
        ).fetchall()
    return [dict(r) for r in rows]


def _get_latest_filing_info(corp_code: str) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT corp_name, filed_at, report_type
            FROM filings
            WHERE corp_code = ?
            ORDER BY filed_at DESC
            LIMIT 1
            """,
            (corp_code,),
        ).fetchone()
    return dict(row) if row else {}


def run(corp_name: str, industry: str) -> dict:
    """기업이 해당 산업에 포함되는지 신고서 세그먼트 기반으로 판정."""

    # 1. corp_code 확보
    corps = find_corps_by_names([corp_name])
    if not corps:
        return {
            "verdict": "error",
            "confidence": None,
            "reason": f"'{corp_name}'을 DART에서 찾을 수 없습니다. 정확한 기업명을 입력하세요.",
            "matching_segments": [],
            "evidence": [],
            "filing_info": {},
        }
    corp = corps[0]
    corp_code = corp["corp_code"]
    resolved_name = corp["corp_name"]

    # 2. DB segments 조회
    segments = _get_segments(corp_code)

    # 3. 없으면 DART 수집 후 재조회
    collected = False
    if not segments:
        collect_by_corps([{
            "corp_code": corp_code,
            "corp_name": resolved_name,
            "stock_code": corp.get("stock_code", ""),
        }])
        segments = _get_segments(corp_code)
        collected = True

    filing_info = _get_latest_filing_info(corp_code)

    # 4. Claude 판정
    if segments:
        seg_lines = "\n".join(
            f"- 사업부문: {s.get('application') or '불명'} | 제품: {s.get('product') or '불명'}"
            + (f" | 매출비중: {s['revenue_share']:.1f}%" if s.get("revenue_share") else "")
            for s in segments
        )
        data_note = ""
    else:
        seg_lines = "(신고서에서 세그먼트 데이터를 추출하지 못했습니다)"
        data_note = "\n데이터가 부족하므로 신뢰도는 낮을 수 있습니다."

    prompt = f"""기업: {resolved_name}
산업: {industry}

아래는 이 기업의 최신 신고서에서 추출한 사업 세그먼트입니다.
{seg_lines}{data_note}

이 기업이 "{industry}" 산업에 포함되는지 판정하세요.

판정 기준 (GICS 기반, 매출 비중 수치가 있으면 수치만으로 판정하고 예외 없음):
- 포함: 해당 산업 매출 비중 60% 이상
- 부분포함: 매출 비중 50% 이상 60% 미만
- 미포함: 매출 비중 50% 미만 (복수 세그먼트를 합산해도 50% 미만이면 미포함)
- 매출 비중 수치가 전혀 없을 때만 사업부문·제품명 키워드로 판단하고 신뢰도를 낮음으로 표시

중요: 매출 비중 수치가 존재하는 경우, 사업 중요성·전략적 의미 등 다른 해석을 개입시키지 마세요.

JSON으로만 반환하세요:
{{
  "verdict": "포함" | "미포함" | "부분포함",
  "confidence": "높음" | "중간" | "낮음",
  "reason": "판정 근거 2~3문장",
  "matching_segments": ["근거가 된 세그먼트 항목 (문자열 목록)"]
}}"""

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()

    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {
            "verdict": "error",
            "confidence": None,
            "reason": f"응답 파싱 실패: {raw[:200]}",
            "matching_segments": [],
            "evidence": segments,
            "filing_info": filing_info,
        }

    result = json.loads(m.group())
    result["evidence"] = segments
    result["filing_info"] = filing_info
    result["resolved_name"] = resolved_name
    return result
