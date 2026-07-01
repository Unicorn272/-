import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import requests
from dotenv import load_dotenv
from functions.db_manager import get_connection, init_db
from functions.dart_collector import download_document, _filing_exists, _parse_and_save_segments

load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")
BASE_URL = "https://opendart.fss.or.kr/api"


def fetch_latest_with_pdf(corp_cls: str) -> tuple[dict, bytes] | None:
    page_no = 1
    while True:
        resp = requests.get(f"{BASE_URL}/list.json", params={
            "crtfc_key": DART_API_KEY,
            "corp_cls": corp_cls,
            "pblntf_ty": "C",
            "page_count": 10,
            "page_no": page_no,
        }, timeout=30)
        data = resp.json()
        if data.get("status") != "000" or not data.get("list"):
            print(f"[{corp_cls}] 수집 실패: {data.get('message')}")
            return None
        for item in data["list"]:
            filing = {
                "corp_name": item["corp_name"],
                "corp_code": item["corp_code"],
                "stock_code": item.get("stock_code", "").strip() or None,
                "report_type": "securities",
                "filed_at": item["rcept_dt"],
                "rcept_no": item["rcept_no"],
                "doc_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item['rcept_no']}",
            }
            print(f"  시도: {item['corp_name']} ({item['rcept_dt']})")
            pdf = download_document(item["rcept_no"])
            if pdf:
                return filing, pdf
        if page_no >= data.get("total_page", 1):
            return None
        page_no += 1


def save_filing(f: dict, pdf_bytes: bytes):
    if _filing_exists(f["rcept_no"]):
        print(f"이미 존재: {f['corp_name']}")
        return

    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO filings
               (corp_name, corp_code, stock_code, report_type, filed_at, doc_url, pdf_blob)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (f["corp_name"], f["corp_code"], f["stock_code"],
             f["report_type"], f["filed_at"], f["doc_url"], pdf_bytes)
        )
        filing_id = cursor.lastrowid
        conn.execute(
            "INSERT OR IGNORE INTO companies (corp_code, corp_name, stock_code) VALUES (?, ?, ?)",
            (f["corp_code"], f["corp_name"], f["stock_code"])
        )

    _parse_and_save_segments(filing_id, pdf_bytes)
    with get_connection() as conn:
        seg_count = conn.execute(
            "SELECT COUNT(*) FROM segments WHERE filing_id = ?", (filing_id,)
        ).fetchone()[0]
    print(f"저장 완료: {f['corp_name']} ({f['filed_at']}) | PDF {len(pdf_bytes)//1024}KB | segments {seg_count}건")


if __name__ == "__main__":
    init_db()

    for corp_cls, label in [("Y", "유가증권"), ("K", "코스닥")]:
        print(f"\n--- {label} 최신 증권신고서 (PDF 있는 것) ---")
        result = fetch_latest_with_pdf(corp_cls)
        if result:
            filing, pdf = result
            save_filing(filing, pdf)
