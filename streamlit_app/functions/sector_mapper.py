import json
import os
import re
import time
import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SECTOR_KEYWORDS = {
    "반도체":      ["반도체", "Semiconductor"],
    "2차전지":     ["2차전지", "배터리", "Battery"],
    "자동차":      ["자동차", "모빌리티"],
    "바이오":      ["헬스케어", "바이오", "제약"],
    "금융":        ["은행", "금융", "보험", "증권"],
    "방산":        ["방산", "방위", "우주"],
    "조선":        ["조선", "해운"],
    "소프트웨어":  ["소프트웨어", "IT", "인터넷", "플랫폼"],
    "에너지/화학": ["에너지", "화학", "석유"],
}

_DIR = os.path.dirname(__file__)
_CACHE_PATH = os.path.join(_DIR, "../db/sector_map_cache.json")
_CACHE_TTL = 7 * 86400  # 7일
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _load_etf_list() -> list:
    try:
        r = requests.get(
            "https://finance.naver.com/api/sise/etfItemList.nhn",
            headers=_HEADERS, timeout=10,
        )
        return r.json().get("result", {}).get("etfItemList", [])
    except Exception:
        return []


def _filter_etfs(keywords: list, all_etfs: list) -> list:
    exclude = ["미국", "글로벌", "US", "Global", "해외", "인버스", "레버리지"]
    result = []
    for etf in all_etfs:
        name = etf.get("itemname", "")
        if any(ex in name for ex in exclude):
            continue
        if any(kw in name for kw in keywords):
            result.append(etf["itemname"])
    return result


def build_sector_map() -> dict:
    """섹터별 ETF → Claude → 기업 목록 빌드 후 캐시 저장."""
    all_etfs = _load_etf_list()

    # 섹터별 ETF 이름 수집
    sector_etfs = {}
    for sector, keywords in SECTOR_KEYWORDS.items():
        matched = _filter_etfs(keywords, all_etfs)
        sector_etfs[sector] = matched[:8]  # 섹터당 최대 8개 ETF

    # 단일 Claude 호출로 전체 섹터 기업 추출
    sector_block = "\n".join(
        f"- {sector}: {', '.join(etfs) if etfs else '(ETF 없음)'}"
        for sector, etfs in sector_etfs.items()
    )
    prompt = f"""아래 한국 섹터별 ETF 목록을 참고해서, 각 섹터의 주요 한국 상장 기업을 최대 12개씩 알려주세요.
미국 상장사(ADR 포함)는 제외하세요.

섹터별 ETF:
{sector_block}

아래 JSON 형식으로만 반환하세요:
{{
  "섹터명": [{{"name": "기업명", "weight": 5.0}}],
  ...
}}
weight는 ETF 내 비중 추정치(%)입니다. 모르면 1.0으로 기재하세요."""

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()

    # JSON 추출
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {}
    data = json.loads(m.group())

    # corp_code 매핑
    from functions.dart_collector import find_corps_by_names
    sector_map = {}
    for sector, companies in data.items():
        names = [c["name"] for c in companies]
        matched = {c["corp_name"]: c for c in find_corps_by_names(names)}
        result = []
        for c in companies:
            corp = matched.get(c["name"], {})
            result.append({
                "name": c["name"],
                "stock_code": corp.get("stock_code", ""),
                "corp_code": corp.get("corp_code", ""),
                "weight": c.get("weight", 1.0),
            })
        sector_map[sector] = result

    cache = {"ts": time.time(), "data": sector_map}
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    return sector_map


def get_sector_map(force: bool = False) -> dict:
    """캐시된 섹터 맵 반환. 7일 초과 또는 force=True면 재빌드."""
    if not force:
        try:
            with open(_CACHE_PATH, encoding="utf-8") as f:
                cache = json.load(f)
            if time.time() - cache.get("ts", 0) < _CACHE_TTL:
                return cache["data"]
        except Exception:
            pass
    return build_sector_map()
