import os, anthropic
from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=512,
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
    messages=[{"role": "user", "content": "MLCC 전기차 최신 정책 동향 검색해줘. 2~3문장 요약."}],
)

with open("test_news_debug.txt", "w", encoding="utf-8") as f:
    for i, block in enumerate(response.content):
        f.write(f"--- block {i}: {type(block).__name__} ---\n")
        f.write(repr(block)[:500] + "\n\n")

print("done")
