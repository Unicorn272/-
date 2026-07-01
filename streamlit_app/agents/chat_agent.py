import json
import os
from typing import Iterator

import anthropic
from dotenv import load_dotenv

load_dotenv()
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), timeout=120.0)

_SYSTEM_TEMPLATE = """당신은 증권신고서 기반 산업 분석 데이터 검색 어시스턴트입니다.
아래 분석 데이터에서 사용자 질문과 관련된 항목을 찾아 원문 그대로 전달하세요.

[분석 산업]
{query}

[분석 데이터 — DART 신고서 원문 기반]
{analysis_json}

## 핵심 규칙 (반드시 준수)
1. 관련 데이터를 찾으면 data 필드 원문을 그대로 인용하고, source 필드 출처를 함께 표시하세요.
2. 인용 전 한 줄로 사용자 질문과 해당 데이터의 연관성을 설명하세요.
3. 데이터에 없는 내용은 "수집된 자료에 없습니다"라고만 답하세요. 추측하거나 일반 지식으로 채우지 마세요.
4. 특정 종목의 매수·매도를 직접 권유하지 마세요.
"""


def stream_response(analysis: dict, query: str, messages: list[dict]) -> Iterator[str]:
    """신고서 분석 데이터에서 사용자 질문에 맞는 데이터를 찾아 스트리밍."""
    system = _SYSTEM_TEMPLATE.format(
        query=query,
        analysis_json=json.dumps(analysis, ensure_ascii=False, indent=2)
    )

    with _client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text
