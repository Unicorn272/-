import os
import io
import json
import time
import zipfile
import requests
import anthropic
from datetime import date, timedelta
from xml.etree import ElementTree as ET
from dotenv import load_dotenv
from .db_manager import get_connection
from .pdf_parser import extract_segments_from_tables, extract_business_content, parse_risk_items

load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")
BASE_URL = "https://opendart.fss.or.kr/api"
_ai = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

REPORT_TYPES = {
    "securities": "C",   # 발행공시 (증권신고서)
    "annual": "A001",    # 사업보고서
}

_CORP_CACHE = os.path.join(os.path.dirname(__file__), "../db/corp_cache.json")


def _load_corp_list() -> list[dict]:
    """DART 전체 상장사 목록 (7일 캐시)"""
    if os.path.exists(_CORP_CACHE):
        if time.time() - os.path.getmtime(_CORP_CACHE) < 7 * 86400:
            with open(_CORP_CACHE, encoding="utf-8") as f:
                return json.load(f)
    resp = requests.get(f"{BASE_URL}/corpCode.xml",
                        params={"crtfc_key": DART_API_KEY}, timeout=60)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_data = zf.read(zf.namelist()[0])
    root = ET.fromstring(xml_data)
    corps = [
        {
            "corp_code": item.findtext("corp_code", ""),
            "corp_name": item.findtext("corp_name", ""),
            "stock_code": item.findtext("stock_code", "").strip(),
        }
        for item in root.findall("list")
        if item.findtext("stock_code", "").strip()
    ]
    os.makedirs(os.path.dirname(_CORP_CACHE), exist_ok=True)
    with open(_CORP_CACHE, "w", encoding="utf-8") as f:
        json.dump(corps, f, ensure_ascii=False)
    return corps


def find_corps_by_names(names: list[str]) -> list[dict]:
    """기업명 리스트 → DART corp_code 매칭 (부분 일치)"""
    corps = _load_corp_list()
    result, seen = [], set()
    for name in names:
        for corp in corps:
            if name in corp["corp_name"] or corp["corp_name"] in name:
                if corp["corp_code"] not in seen:
                    seen.add(corp["corp_code"])
                    result.append(corp)
                break
    return result


def _fetch_one_filing(corp_code: str, pblntf_ty: str, bgn_de: str, end_de: str,
                      report_nm_filter: str = None) -> dict | None:
    """조건에 맞는 가장 최근 공시 1건 반환 (목록만, 다운로드 없음)"""
    page_no = 1
    while True:
        resp = requests.get(f"{BASE_URL}/list.json", params={
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "pblntf_ty": pblntf_ty,
            "bgn_de": bgn_de,
            "end_de": end_de,
            "page_count": 100,
            "page_no": page_no,
        }, timeout=30)
        data = resp.json()
        if data.get("status") != "000" or not data.get("list"):
            return None
        for item in data["list"]:
            if report_nm_filter:
                nm = item.get("report_nm", "")
                if not (nm.startswith(report_nm_filter) or nm.startswith(f"[정정]{report_nm_filter}")):
                    continue
            return item
        if page_no >= data.get("total_page", 1):
            return None
        page_no += 1


def _item_to_filing(item: dict, report_type: str) -> dict:
    return {
        "corp_name": item["corp_name"],
        "corp_code": item["corp_code"],
        "stock_code": item.get("stock_code", "").strip() or None,
        "report_type": report_type,
        "filed_at": item["rcept_dt"],
        "rcept_no": item["rcept_no"],
        "doc_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item['rcept_no']}",
    }


def _save_risk_items(filing_id: int, doc_bytes: bytes):
    items = parse_risk_items(doc_bytes)
    if not items:
        return
    with get_connection() as conn:
        conn.execute("DELETE FROM risk_items WHERE filing_id = ?", (filing_id,))
        for item in items:
            conn.execute(
                """INSERT INTO risk_items
                   (filing_id, item_label, parent_label, sub_index, title, content)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (filing_id, item["item_label"], item["parent_label"],
                 item["sub_index"], item["title"], item["content"]),
            )


def _has_recent_filing(corp_code: str) -> bool:
    """DB에 2년 이내 신고서가 있으면 True → DART 재수집 스킵"""
    from datetime import datetime
    cutoff = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
    with get_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM filings WHERE corp_code=? AND filed_at>=? LIMIT 1",
            [corp_code, cutoff]
        ).fetchone() is not None


def _save_filing_and_segments(f: dict, doc: bytes):
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO filings
               (corp_name, corp_code, stock_code, report_type, filed_at, doc_url)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (f["corp_name"], f["corp_code"], f["stock_code"],
             f["report_type"], f["filed_at"], f["doc_url"])
        )
        filing_id = cursor.lastrowid
        conn.execute(
            "INSERT OR IGNORE INTO companies (corp_code, corp_name, stock_code) VALUES (?, ?, ?)",
            (f["corp_code"], f["corp_name"], f["stock_code"])
        )
    _parse_and_save_segments(filing_id, doc)
    if f["report_type"] == "securities":
        _save_risk_items(filing_id, doc)


def collect_by_corps(corps: list[dict], bgn_de: str = None, end_de: str = None) -> list[str]:
    """기업당 보고서 1건 수집: 증권신고서 우선, 없으면 사업보고서 대체.
    반환: 증권신고서가 없어서 사업보고서로 대체된 기업명 리스트.
    """
    if end_de is None:
        end_de = date.today().strftime("%Y%m%d")
    if bgn_de is None:
        bgn_de = (date.today() - timedelta(days=1825)).strftime("%Y%m%d")

    fallback_corps: list[str] = []

    for corp in corps:
        if _has_recent_filing(corp["corp_code"]):
            print(f"  스킵(캐시): {corp['corp_name']}")
            continue

        # 1순위: 2년 이내 최신 증권신고서 (발행실적보고서 제외)
        item = _fetch_one_filing(corp["corp_code"], "C", bgn_de, end_de, report_nm_filter="증권신고서")
        if item:
            f = _item_to_filing(item, "securities")
            if not _filing_exists(f["rcept_no"]):
                doc = download_document(f["rcept_no"])
                if doc:
                    _save_filing_and_segments(f, doc)
                    print(f"  저장: {f['corp_name']} {f['filed_at']} (securities)")
            continue

        # 2순위: 가장 최근 사업보고서 (기간 제한 없이)
        fallback_corps.append(corp["corp_name"])
        item = _fetch_one_filing(corp["corp_code"], "A", bgn_de, end_de, report_nm_filter="사업보고서")
        if item:
            f = _item_to_filing(item, "annual")
            if not _filing_exists(f["rcept_no"]):
                doc = download_document(f["rcept_no"])
                if doc:
                    _save_filing_and_segments(f, doc)
                    print(f"  저장(대체): {f['corp_name']} {f['filed_at']} (annual)")

    return fallback_corps


def _fetch_list_page(corp_cls, pblntf_ty, bgn_de, end_de, page_no):
    resp = requests.get(f"{BASE_URL}/list.json", params={
        "crtfc_key": DART_API_KEY,
        "corp_cls": corp_cls,
        "pblntf_ty": pblntf_ty,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_count": 100,
        "page_no": page_no,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_filings(bgn_de=None, end_de=None):
    if end_de is None:
        end_de = date.today().strftime("%Y%m%d")
    if bgn_de is None:
        bgn_de = (date.today() - timedelta(days=730)).strftime("%Y%m%d")

    results = []
    for report_type, pblntf_ty in REPORT_TYPES.items():
        for corp_cls in ("Y", "K"):
            page_no = 1
            while True:
                data = _fetch_list_page(corp_cls, pblntf_ty, bgn_de, end_de, page_no)
                if data.get("status") != "000":
                    break
                for item in data.get("list", []):
                    results.append({
                        "corp_name": item["corp_name"],
                        "corp_code": item["corp_code"],
                        "stock_code": item.get("stock_code", "").strip() or None,
                        "report_type": report_type,
                        "filed_at": item["rcept_dt"],
                        "rcept_no": item["rcept_no"],
                        "doc_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item['rcept_no']}",
                    })
                if page_no >= data.get("total_page", 1):
                    break
                page_no += 1

    return results


def download_document(rcept_no):
    """document.xml → ZIP 압축 해제 → 가장 큰 XML/HTML 파일 반환"""
    resp = requests.get(f"{BASE_URL}/document.xml", params={
        "crtfc_key": DART_API_KEY,
        "rcept_no": rcept_no,
    }, timeout=60)
    resp.raise_for_status()
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            doc_files = [n for n in zf.namelist() if n.lower().endswith((".xml", ".htm", ".html"))]
            if not doc_files:
                return None
            doc_files.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
            return zf.read(doc_files[0])
    except zipfile.BadZipFile:
        return None


def _filing_exists(rcept_no):
    with get_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM filings WHERE doc_url LIKE ?", (f"%{rcept_no}%",)
        ).fetchone() is not None


def _parse_and_save_segments(filing_id: int, pdf_bytes: bytes):
    """사업의 내용 테이블 직접 파싱 → 실패 시 Claude Sonnet 폴백 → segments 저장"""
    items = extract_segments_from_tables(pdf_bytes)

    if not items:
        text = extract_business_content(pdf_bytes)
        if text.strip():
            resp = _ai.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": f"""다음 텍스트에서 사업부별 제품명·적용분야·매출비중을 추출하세요.
텍스트에 있는 내용만, 해석·추가 없이 그대로 추출하세요.

JSON 배열만 반환:
[{{"product": "제품명", "application": "적용분야 또는 사업부문", "revenue_share": 매출비중숫자또는null}}]

텍스트:
{text[:6000]}"""
                }]
            )
            try:
                raw = resp.content[0].text
                start, end = raw.find("["), raw.rfind("]") + 1
                items = json.loads(raw[start:end]) if start != -1 else []
            except Exception:
                items = []

    if not items:
        return

    with get_connection() as conn:
        for item in items:
            conn.execute(
                """INSERT INTO segments (filing_id, application, product, revenue_share, industry_tags)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    filing_id,
                    item.get("application"),
                    item.get("product"),
                    item.get("revenue_share"),
                    "[]",
                )
            )


def collect_and_save(bgn_de=None, end_de=None):
    filings = fetch_filings(bgn_de, end_de)
    print(f"수집된 신고서: {len(filings)}건")

    saved = 0
    for f in filings:
        if _filing_exists(f["rcept_no"]):
            continue
        pdf_bytes = download_document(f["rcept_no"])
        with get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO filings
                   (corp_name, corp_code, stock_code, report_type, filed_at, doc_url)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (f["corp_name"], f["corp_code"], f["stock_code"],
                 f["report_type"], f["filed_at"], f["doc_url"])
            )
            filing_id = cursor.lastrowid
            conn.execute(
                """INSERT OR IGNORE INTO companies (corp_code, corp_name, stock_code)
                   VALUES (?, ?, ?)""",
                (f["corp_code"], f["corp_name"], f["stock_code"])
            )

        if pdf_bytes:
            _parse_and_save_segments(filing_id, pdf_bytes)

        saved += 1
        print(f"저장: {f['corp_name']} ({f['filed_at']})")

    print(f"신규 저장: {saved}건")
