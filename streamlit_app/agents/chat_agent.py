import json
import os
from typing import Iterator

import anthropic
from dotenv import load_dotenv

load_dotenv()
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_SYSTEM_TEMPLATE = """당신은 증권신고서 기반 산업 분석 어시스턴트입니다.
아래 분석 데이터를 근거로 투자 시사점을 설명하세요.

[분석 산업]
{query}

[분석 데이터 — DART 신고서 원문 기반]
{analysis_json}

## 핵심 규칙 (반드시 준수)
1. 신고서 수치를 인용할 때는 반드시 data 항목의 source 필드에 있는 출처를 함께 명시하세요.
2. EV 판매량, 탄산리튬 가격, 배터리 ASP, ESS 설치량, 공장 가동률 등 신고서에 없는 시장 수치가 필요하면 web_search 툴로 검색 후 출처(기관/날짜)를 명시하세요.
3. 신고서에도 없고 검색도 안 되는 수치는 "해당 데이터가 수집된 자료에 없습니다"라고 답하세요. 절대 추측이나 일반적 지식으로 수치를 만들어내지 마세요.
4. 3~5문장으로 간결하게 답변하세요.
5. 특정 종목의 매수·매도를 직접 권유하지 마세요.
"""


def stream_response(analysis: dict, query: str, messages: list[dict]) -> Iterator[str]:
    """신고서 분석 데이터 + web_search로 투자 시사점 스트리밍."""
    system = _SYSTEM_TEMPLATE.format(
        query=query,
        analysis_json=json.dumps(analysis, ensure_ascii=False, indent=2)
    )

    with _client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=system,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text
