import json
import os
import re
import anthropic
from dotenv import load_dotenv
from functions.db_manager import get_connection

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _parse_json(raw: str) -> dict:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    depth, start = 0, -1
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    return json.loads(raw[start:i + 1])
                except json.JSONDecodeError:
                    pass
    raise ValueError(f"분석 결과 JSON 파싱 실패. 응답 앞부분: {raw[:200]}")


def run(extracted: dict, query: str, corp_codes: list[str]) -> dict:
    """
    기업별 risk_items 텍스트 전체 → Claude Sonnet 1회 호출 → 덱 구성 + 리서치 데이터
    industry_analysis 테이블에 캐시 저장 (동일 산업+기업 조합이면 즉시 반환)
    """
    industry_key = re.sub(r'\s+', '', query).lower()
    codes_str = ",".join(sorted(corp_codes))

    # 캐시 확인
    with get_connection() as conn:
        row = conn.execute(
            "SELECT result FROM industry_analysis WHERE industry_key=? AND corp_codes=?",
            [industry_key, codes_str]
        ).fetchone()
    if row:
        return json.loads(row["result"])

    texts: dict = extracted["texts"]
    corp_filings: list = extracted["corp_filings"]

    if not texts:
        return {"deck_structure": [], "research_data": [], "data_limitations": ["분석할 데이터가 없습니다."]}

    filing_refs = ", ".join(
        f"{c['corp_name']} {c['report_type']} {c['filed_at']}" for c in corp_filings
    )
    combined = "\n\n".join(
        f"=== {name} 투자위험요소 ===\n{text}" for name, text in texts.items()
    )

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": f"""다음 증권신고서 투자위험요소 텍스트로 컨설팅 덱 구성과 리서치 데이터를 작성하세요.

## 참조 신고서
{filing_refs}

## 기업별 투자위험요소
{combined[:200_000]}

## 출력 형식 (JSON만 반환)
{{
  "deck_structure": [
    {{
      "section_no": 1,
      "section_title": "섹션 제목",
      "chapters": [
        {{"no": 1, "title": "장 제목", "description": "이 장에서 다룰 내용 1~2문장"}},
        {{"no": 2, "title": "장 제목", "description": "..."}}
      ],
      "key_message": "→ 이 섹션의 핵심 메시지"
    }}
  ],
  "research_data": [
    {{
      "topic": "토픽명 (예: 경쟁 구도, 규제 환경, 시장 현황)",
      "items": [
        {{
          "text": "항목 설명",
          "data": "신고서 원문 수치·문장 그대로 인용. 신고서에 없으면 반드시 빈 문자열. 해석·계산·추가 금지.",
          "source": "기업명 신고서종류 연월"
        }}
      ]
    }}
  ],
  "data_limitations": ["한계 1", "한계 2"]
}}

규칙:
- deck_structure: 3개 섹션, 섹션당 3~4개 장
  - Section 1: 산업 현황 및 경쟁 구도
  - Section 2: 위험 요인 분석 (규제·기술·거시환경)
  - Section 3: 핵심 인사이트 및 전략적 시사점
- research_data: 4~6개 토픽, 토픽당 3~6개 항목
- source는 반드시 "기업명 증권신고서 연월" 또는 "기업명 사업보고서 연월" 형식
- 신고서에 없는 내용은 절대 추가하지 말 것
- data 필드: 신고서 원문 수치·문장 그대로만. 신고서에 없으면 반드시 빈 문자열. 해석·계산·추가 절대 금지."""
        }]
    )

    result = _parse_json(resp.content[0].text)

    # 캐시 저장
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO industry_analysis
               (industry_key, corp_codes, query, result)
               VALUES (?, ?, ?, ?)""",
            [industry_key, codes_str, query, json.dumps(result, ensure_ascii=False)]
        )

    return result
