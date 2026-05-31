from functions.db_manager import get_connection


def _get_risk_text(filing_id: int) -> str:
    with get_connection() as conn:
        items = conn.execute(
            "SELECT title, content FROM risk_items WHERE filing_id = ? ORDER BY id",
            (filing_id,)
        ).fetchall()
    if not items:
        return ""
    return "\n\n".join(
        f"[{r['title']}]\n{r['content']}" for r in items if r["content"]
    )


def run(companies: list[dict]) -> dict:
    """
    risk_items 텍스트를 기업별로 읽어 반환. Claude 호출 없음.
    반환: {"texts": {corp_name: risk_text}, "corp_filings": [{corp_name, filed_at, report_type}]}
    """
    texts: dict[str, str] = {}
    corp_filings: list[dict] = []
    seen = set()

    for c in companies:
        name = c["corp_name"]
        if name in seen:
            continue
        seen.add(name)

        with get_connection() as conn:
            row = conn.execute(
                "SELECT report_type, filed_at FROM filings WHERE id=?", [c["filing_id"]]
            ).fetchone()
        if not row:
            continue

        text = _get_risk_text(c["filing_id"])
        if text.strip():
            texts[name] = text[:60_000]  # 기업당 최대 60,000자

        corp_filings.append({
            "corp_name": name,
            "report_type": row["report_type"],
            "filed_at": row["filed_at"],
        })

    return {"texts": texts, "corp_filings": corp_filings}
