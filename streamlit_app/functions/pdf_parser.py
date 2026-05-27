import re
import warnings
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

SECTION_KEYWORDS = {
    "사업의 내용": ["II. 사업의 내용", "Ⅱ. 사업의 내용", "사업의 개요"],
    "투자위험요소": ["III. 투자위험요소", "Ⅲ. 투자위험요소", "투자 위험요소"],
}

SECTION_ENDS = {
    "사업의 내용": ["III.", "Ⅲ.", "투자위험요소"],
    "투자위험요소": ["IV.", "Ⅳ.", "자금의 사용목적"],
}


def _table_to_markdown(table: Tag) -> str:
    """BeautifulSoup <table> 태그 → 마크다운 테이블 문자열."""
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)

    if not rows:
        return ""

    col_count = max(len(r) for r in rows)
    # 열 수 맞춤
    rows = [r + [""] * (col_count - len(r)) for r in rows]

    col_widths = [max(len(r[i]) for r in rows) for i in range(col_count)]

    def fmt_row(r):
        return "| " + " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(r)) + " |"

    lines = [fmt_row(rows[0])]
    lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")
    for row in rows[1:]:
        lines.append(fmt_row(row))
    return "\n".join(lines)


def _soup_to_text(soup: BeautifulSoup) -> str:
    """HTML/XML 파싱 후 table은 마크다운으로, 나머지는 일반 텍스트로 변환."""
    for table in soup.find_all("table"):
        md = _table_to_markdown(table)
        table.replace_with(f"\n{md}\n")
    return soup.get_text(separator="\n")


def _is_section_header(line: str, keywords: list[str]) -> bool:
    stripped = line.strip()
    return any(stripped == kw or stripped.startswith(kw + " ") or stripped.startswith(kw + "\t") for kw in keywords)


def _has_real_content(chunks: list[str]) -> bool:
    return any(len(line.strip()) > 50 for line in chunks)


def _extract_section(doc_bytes: bytes, section: str) -> str:
    text = doc_bytes.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(text, features="html.parser")
    full_text = _soup_to_text(soup)

    start_kw = SECTION_KEYWORDS[section]
    end_kw = SECTION_ENDS[section]

    lines = full_text.splitlines()
    collecting = False
    chunks = []

    for line in lines:
        if not collecting:
            if _is_section_header(line, start_kw):
                collecting = True
                chunks = []
        if collecting:
            if chunks and _is_section_header(line, end_kw):
                if _has_real_content(chunks):
                    break
                collecting = False
                chunks = []
                continue
            chunks.append(line)

    # 연속 빈 줄 3개 이상 → 1개로 압축
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(chunks))
    return result


def extract_business_content(doc_bytes: bytes) -> str:
    return _extract_section(doc_bytes, "사업의 내용")


# 사업위험 하위 섹션 시작/끝 키워드 (신고서마다 번호/한자 표기 다름)
_BIZ_RISK_START = ["1. 사업위험", "가. 사업위험", "Ⅰ. 사업위험"]
_BIZ_RISK_END   = ["2. 회사위험", "나. 회사위험", "Ⅱ. 회사위험"]


def extract_risk_factors(doc_bytes: bytes) -> str:
    """투자위험요소 전체 섹션 추출."""
    return _extract_section(doc_bytes, "투자위험요소")


def extract_business_risk(doc_bytes: bytes) -> str:
    """투자위험요소 > 사업위험 하위 섹션만 추출. 없으면 전체 섹션 반환."""
    full = _extract_section(doc_bytes, "투자위험요소")
    lines = full.splitlines()

    collecting = False
    chunks = []
    for line in lines:
        stripped = line.strip()
        if not collecting:
            if _is_section_header(line, _BIZ_RISK_START):
                collecting = True
                chunks = []
        if collecting:
            if chunks and _is_section_header(line, _BIZ_RISK_END):
                break
            chunks.append(line)

    if not _has_real_content(chunks):
        return full  # 하위 섹션 구분 없는 신고서면 전체 반환

    result = re.sub(r"\n{3,}", "\n\n", "\n".join(chunks))
    return result
