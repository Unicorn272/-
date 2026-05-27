import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def run(extracted: dict) -> dict:
    """
    추출 데이터 → Porter 5 Forces + PESTEL 분석 결과 반환
    """
    data = extracted["data"]
    news = extracted.get("news_supplements", {})

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": f"""다음 데이터를 바탕으로 Porter 5 Forces와 PESTEL 분석을 수행하세요.

## 입력 데이터
경쟁사: {json.dumps(data.get("competitors", []), ensure_ascii=False)}
규제: {json.dumps(data.get("regulations", []), ensure_ascii=False)}
위협요인: {json.dumps(data.get("threats", []), ensure_ascii=False)}
시장 데이터: {json.dumps(data.get("market_data", []), ensure_ascii=False)}
뉴스 보완 (정성 맥락만): {json.dumps(news, ensure_ascii=False)}

## 출력 형식 (JSON만 반환)
{{
  "five_forces": {{
    "competitive_rivalry": {{"score": 1~5, "summary": "", "evidence": ["출처: 신고서명 연월"]}},
    "supplier_power": {{"score": 1~5, "summary": "", "evidence": []}},
    "buyer_power": {{"score": 1~5, "summary": "", "evidence": []}},
    "threat_of_substitutes": {{"score": 1~5, "summary": "", "evidence": []}},
    "threat_of_new_entrants": {{"score": 1~5, "summary": "", "evidence": []}}
  }},
  "pestel": {{
    "political": {{"summary": "", "evidence": [], "source_type": "신고서|뉴스"}},
    "economic": {{"summary": "", "evidence": [], "source_type": "신고서|뉴스"}},
    "social": {{"summary": "", "evidence": [], "source_type": "뉴스"}},
    "technological": {{"summary": "", "evidence": [], "source_type": "신고서|뉴스"}},
    "environmental": {{"summary": "", "evidence": [], "source_type": "신고서|뉴스"}},
    "legal": {{"summary": "", "evidence": [], "source_type": "신고서|뉴스"}}
  }},
  "key_insights": ["인사이트 1", "인사이트 2", "인사이트 3"],
  "data_limitations": ["한계 1", "한계 2"]
}}

규칙:
- evidence는 반드시 "출처: 신고서명 연월" 또는 "출처: 매체명 연월" 형식
- 뉴스 데이터는 수치 없이 정성적 맥락만 사용
- 데이터가 부족한 항목은 data_limitations에 명시"""
        }]
    )

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
    raise ValueError("분석 결과 JSON 파싱 실패")
