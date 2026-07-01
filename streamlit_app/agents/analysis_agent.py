import json
import os
import re
import anthropic
from dotenv import load_dotenv
from functions.db_manager import get_connection

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _fix_json_newlines(text: str) -> str:
    """JSON 문자열 값 내 이스케이프 안 된 줄바꿈·탭을 수정."""
    result = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            pass
        elif in_string and ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def _parse_json(raw: str) -> dict:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    # JSON 문자열 내 줄바꿈 수정
    raw = _fix_json_newlines(raw)
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
    codes_str = ",".join(sorted(set(corp_codes)))

    # 캐시 확인 — 동일 쿼리+기업 조합, 없으면 동일 기업 조합만으로도 히트
    with get_connection() as conn:
        row = conn.execute(
            "SELECT result FROM industry_analysis WHERE industry_key=? AND corp_codes=?",
            [industry_key, codes_str]
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT result FROM industry_analysis WHERE corp_codes=? ORDER BY id DESC LIMIT 1",
                [codes_str]
            ).fetchone()
    if row:
        return json.loads(row["result"])

    texts: dict = extracted["texts"]
    corp_filings: list = extracted["corp_filings"]

    if not texts:
        return {"sections": [], "data_limitations": ["분석할 데이터가 없습니다."]}

    filing_refs = ", ".join(
        f"{c['corp_name']} {c['report_type']} {c['filed_at']}" for c in corp_filings
    )
    combined = "\n\n".join(
        f"=== {name} 투자위험요소 ===\n{text}" for name, text in texts.items()
    )

    prompt = f"""다음 증권신고서 투자위험요소 텍스트로 컨설팅 덱 구성과 리서치 데이터를 작성하세요.

## 참조 신고서
{filing_refs}

## 기업별 투자위험요소
{combined[:200_000]}

## 출력 형식 (JSON만 반환)
{{
  "sections": [
    {{
      "section_no": 1,
      "section_title": "섹션 제목",
      "chapters": [
        {{
          "no": 1,
          "title": "장 제목",
          "description": "이 장에서 다룰 내용 1~2문장",
          "data": [
            {{
              "text": "항목 설명",
              "data": "신고서 원문 수치·문장 그대로 인용 (없으면 빈 문자열)",
              "source": "기업명 신고서종류 연월"
            }}
          ]
        }}
      ],
      "key_message": "→ 이 섹션의 핵심 메시지"
    }}
  ],
  "data_limitations": ["한계 1", "한계 2"]
}}

규칙:
- sections: 3개, 섹션당 3~4개 장
  - Section 1: 산업 현황 및 경쟁 구도
  - Section 2: 위험 요인 분석 (규제·기술·거시환경)
  - Section 3: 핵심 인사이트 및 전략적 시사점
- 장당 data 항목 3~6개
- source: "기업명 신고서종류 연월" 기본. 원문에 출처 명시된 경우 슬래시로 추가
  예: "LG에너지솔루션 증권신고서 202602 / SNE리서치(2025.08)"
- 분석 대상 기업이 1개인 경우, 주어는 해당 기업명 대신 산업명("{query}")으로 작성 (예: "KG모빌리티는~" 대신 "자동차 산업은~")
- 신고서에 없는 내용 절대 추가 금지
- data 필드: 원문에 표가 있으면 마크다운 테이블(| 형식) 그대로 인용. 수치·문장은 원문 그대로. 없으면 반드시 빈 문자열.
- 다음 항목은 어떤 섹션에도 포함하지 말 것: 주식매수선택권(스톡옵션) 부여 현황·행사가격·부여 인원, 임직원·경영진 개인 보수·급여·지분율, 주주 구성·최대주주 지분율 등 지배구조 세부사항."""

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=32000,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        raw_text = stream.get_final_text()

    result = _parse_json(raw_text)

    # 캐시 저장
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO industry_analysis
               (industry_key, corp_codes, query, result)
               VALUES (?, ?, ?, ?)""",
            [industry_key, codes_str, query, json.dumps(result, ensure_ascii=False)]
        )

    return result
