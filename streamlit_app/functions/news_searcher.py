import os
from datetime import date, timedelta
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# PESTEL 카테고리별 허용 기간
_RECENCY_DAYS = {
    "Economic": 180,   # 시장 수치 — 6개월
    "Political": 365,  # 규제·정책 — 1년
    "Legal": 365,
    "Social": 365,     # 산업 트렌드 — 1년
    "Technological": 365,
    "Environmental": 365,
}


def search_news(topic: str, pestel_category: str) -> str:
    """
    주어진 주제에 대한 뉴스를 검색해 정성적 맥락만 반환.
    수치는 제외하고 정책·트렌드·업계 동향만 2~3문장 요약.
    """
    days = _RECENCY_DAYS.get(pestel_category, 365)
    cutoff = (date.today() - timedelta(days=days)).strftime("%Y년 %m월")

    prompt = f"""웹 검색으로 다음 주제의 최신 동향을 찾아주세요.

주제: {topic}
PESTEL 분류: {pestel_category}
기간 제한: {cutoff} 이후 발행된 내용만 인용

출처 우선순위 (높은 순서대로 우선 인용):
1순위: 정부·기관 발표 기반 뉴스 (산업부, 한국은행, IEA, SEMI 등 원본 있는 것)
2순위: 전문지 (전자신문, 디일렉, Reuters, Bloomberg)
3순위: 종합 일간지 (한국경제, 매일경제, 연합뉴스)
제외: 커뮤니티, 블로그, 증권사 리포트 요약본

규칙:
1. 수치(숫자, %, 금액)는 포함하지 말 것
2. 정성적 맥락(정책 방향, 트렌드, 업계 동향)만 2~3문장으로 요약
3. 출처 매체명과 우선순위 등급을 끝에 표기 (예: [전자신문 - 2순위])
4. 기간 내 신뢰 출처가 없을 경우 "신뢰 출처 없음"으로 표기"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    # 검색 결과가 여러 TextBlock에 분산되므로 모두 합치기
    parts = []
    for block in response.content:
        if hasattr(block, "text") and block.text.strip():
            parts.append(block.text)
    return "".join(parts)
