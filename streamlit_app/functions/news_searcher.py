import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def fetch_news_companies(query: str) -> list[str]:
    """web_search로 관련주 검색 → 한국 상장 기업명 추출."""
    prompt = f"""웹 검색으로 "{query} 관련주", "{query} 기업 종목"을 검색하여
"{query}" 산업과 직접 관련된 한국 상장 기업명을 최대한 많이 수집하세요.

규칙:
- 해당 산업이 핵심 사업인 기업 우선 (순수 플레이어)
- 삼성전자, LG전자, SK하이닉스 등 대기업은 해당 산업 매출 비중이 높은 경우만 포함
- 한국거래소(KRX) 상장 기업명만
- JSON 배열만 반환, 중복 제거, 최대 30개

["기업A", "기업B", ...]"""

    r = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": prompt}],
    )
    # 마지막 text block이 최종 답변
    raw = ""
    for block in r.content:
        if hasattr(block, "text") and block.text.strip():
            raw = block.text
    start, end = raw.find("["), raw.rfind("]") + 1
    try:
        return json.loads(raw[start:end]) if start != -1 else []
    except Exception:
        return []


