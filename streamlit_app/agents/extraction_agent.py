from functions.db_manager import get_connection


def _get_risk_text(filing_id: int) -> str:
    with get_connection() as conn:
        items = conn.execute(
            "SELECT title, content FROM risk_items WHERE filing_id = ? ORDER BY id",
            (filing_id,),
        ).fetchall()
    if not items:
        return ""
    return "\n\n".join(
        f"[{r['title']}]\n{r['content']}" for r in items if r["content"]
    )


def run(companies: list[dict], mode: str = "A") -> dict:
    """
    Mode A: 해당 산업 기업들의 증권신고서 중 가장 최근 2건만 추출
    Mode B: 기업당 보유한 증권신고서 전체 추출
    반환: {"texts": {corp_name: risk_text}, "corp_filings": [{corp_name, filed_at, report_type}]}
    """
    corp_codes = [c["corp_code"] for c in companies if c.get("corp_code")]
    if not corp_codes:
        return {"texts": {}, "corp_filings": []}

    placeholders = ",".join("?" * len(corp_codes))

    with get_connection() as conn:
        if mode == "A":
            rows = conn.execute(f"""
                SELECT f.id, f.corp_name, f.corp_code, f.filed_at, f.report_type
                FROM filings f
                WHERE f.corp_code IN ({placeholders}) AND f.report_type = 'securities'
                ORDER BY f.filed_at DESC
                LIMIT 2
            """, corp_codes).fetchall()
        else:
            rows = conn.execute(f"""
                SELECT f.id, f.corp_name, f.corp_code, f.filed_at, f.report_type
                FROM filings f
                WHERE f.corp_code IN ({placeholders}) AND f.report_type = 'securities'
                ORDER BY f.filed_at DESC
            """, corp_codes).fetchall()

    texts: dict[str, str] = {}
    corp_filings: list[dict] = []

    for row in rows:
        name = row["corp_name"]
        text = _get_risk_text(row["id"])

        corp_filings.append({
            "corp_name": name,
            "report_type": row["report_type"],
            "filed_at": row["filed_at"],
        })

        if text.strip():
            existing = texts.get(name, "")
            combined = f"{existing}\n\n---\n\n[신고서: {row['filed_at']}]\n{text}" if existing else f"[신고서: {row['filed_at']}]\n{text}"
            texts[name] = combined[:80_000]

    return {"texts": texts, "corp_filings": corp_filings}
