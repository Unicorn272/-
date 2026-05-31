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


_ITEM_START = re.compile(r'^(?:\|\s*)?(?:\[)?([가나다라마바사아자차카타파하])\. ', re.MULTILINE)
_SUB_ITEM = re.compile(r'^(?:\|\s*)?(?:\[)?([가나다라마바사아자차카타파하])-(\d+)\. ', re.MULTILINE)
# 대괄호 헤더 방식 폴백: [제목] 형식
_BRACKET_HEADER = re.compile(r'^\[([^\]]{5,80})\]$', re.MULTILINE)


def _extract_title(text: str, prefix_pattern: str) -> str:
    first_line = text.splitlines()[0].strip().lstrip('| ')
    return re.sub(prefix_pattern, '', first_line)[:100].rstrip()


def parse_risk_items(doc_bytes: bytes) -> list[dict]:
    """사업위험 섹션을 항목 단위로 분리해 반환.

    Structure A (병렬): 가/나/다/라 → parent_label=None
    Structure B (중첩): 가/나(다-1/다-2/라-1...)/사 → 하위항목은 parent_label='나'
    """
    section = extract_business_risk(doc_bytes)
    if not section.strip():
        return []

    top_matches = list(_ITEM_START.finditer(section))

    # 가/나/다 패턴 없으면 대괄호 헤더 방식으로 폴백
    if not top_matches:
        bracket_matches = list(_BRACKET_HEADER.finditer(section))
        if not bracket_matches:
            return []
        _labels = list("가나다라마바사아자차카타파하")
        items = []
        for i, m in enumerate(bracket_matches):
            title = m.group(1).strip()
            start = m.start()
            end = bracket_matches[i + 1].start() if i + 1 < len(bracket_matches) else len(section)
            content = section[start:end].strip()
            items.append({
                "item_label": _labels[i % len(_labels)],
                "parent_label": None,
                "sub_index": None,
                "title": title,
                "content": content,
            })
        return items

    items = []
    for i, m in enumerate(top_matches):
        label = m.group(1)
        start = m.start()
        end = top_matches[i + 1].start() if i + 1 < len(top_matches) else len(section)
        block = section[start:end].strip()

        sub_matches = list(_SUB_ITEM.finditer(block))

        if not sub_matches:
            # Structure A: 단일 항목
            title = _extract_title(block, r'^[가나다라마바사아자차카타파하]\.\s*')
            items.append({
                "item_label": label,
                "parent_label": None,
                "sub_index": None,
                "title": title,
                "content": block,
            })
        else:
            # Structure B: 상위 항목 본문 + 하위 항목들
            intro_end = sub_matches[0].start()
            intro = block[:intro_end].strip()
            title = _extract_title(block, r'^[가나다라마바사아자차카타파하]\.\s*')
            items.append({
                "item_label": label,
                "parent_label": None,
                "sub_index": None,
                "title": title,
                "content": intro or block,
            })
            for j, sm in enumerate(sub_matches):
                sub_label = sm.group(1)
                sub_idx = int(sm.group(2))
                sub_start = sm.start()
                sub_end = sub_matches[j + 1].start() if j + 1 < len(sub_matches) else len(block)
                sub_content = block[sub_start:sub_end].strip()
                sub_title = _extract_title(sub_content, r'^[가나다라마바사아자차카타파하]-\d+\.\s*')
                items.append({
                    "item_label": sub_label,
                    "parent_label": label,
                    "sub_index": sub_idx,
                    "title": sub_title,
                    "content": sub_content,
                })

    return items


def extract_business_content(doc_bytes: bytes) -> str:
    return _extract_section(doc_bytes, "사업의 내용")


# ── 테이블 기반 세그먼트 직접 파싱 ────────────────────────────────────────────

_PRODUCT_HEADERS     = {"주요 제품", "제품", "주요제품", "주요품목", "품목", "제품명",
                        "주요 품목", "제품/서비스", "주요제품 및 서비스"}
_APPLICATION_HEADERS = {"사업부문", "부문", "세그먼트", "사업부", "사업", "분야",
                        "적용분야", "사업 부문", "구분"}
_REVENUE_HEADERS     = {"매출비중", "비중", "매출 비중", "구성비", "비율",
                        "매출비율", "비 중", "비중(%)"}
_SKIP_ROWS           = {"합계", "계", "total", "소계", "-", ""}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _match_header(cell: str, keywords: set) -> bool:
    c = _norm(cell)
    return c in keywords or any(kw in c for kw in keywords)


def _parse_revenue_value(text: str) -> float | None:
    cleaned = text.replace(",", "").replace("%", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if not m:
        return None
    val = float(m.group(1))
    # 소수 형태(0.46)면 % 변환, 100 초과면 매출액(원단위)이므로 무시
    if val <= 0:
        return None
    if val < 1:
        return round(val * 100, 2)
    return val if val <= 100 else None


def _parse_markdown_rows(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        if not line.startswith("|"):
            break
        if re.fullmatch(r"[\|\s\-:]+", line):  # 구분선
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if any(cells):
            rows.append(cells)
    return rows


def extract_segments_from_tables(doc_bytes: bytes) -> list[dict]:
    """사업의 내용 섹션 테이블에서 product/application/revenue_share 규칙 기반 추출.
    Claude 호출 없이 순수 파싱."""
    section_text = extract_business_content(doc_bytes)
    lines = section_text.splitlines()

    results = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("|"):
            i += 1
            continue

        # 테이블 라인 수집
        table_lines = []
        while i < len(lines) and lines[i].startswith("|"):
            table_lines.append(lines[i])
            i += 1

        rows = _parse_markdown_rows(table_lines)
        if len(rows) < 2:
            continue

        headers = [_norm(h) for h in rows[0]]
        prod_idx = next((j for j, h in enumerate(headers) if _match_header(h, _PRODUCT_HEADERS)), -1)
        app_idx  = next((j for j, h in enumerate(headers) if _match_header(h, _APPLICATION_HEADERS)), -1)
        rev_idx  = next((j for j, h in enumerate(headers) if _match_header(h, _REVENUE_HEADERS)), -1)

        # 제품 컬럼이나 매출비중 컬럼 중 하나라도 없으면 무관한 테이블
        if prod_idx == -1 or rev_idx == -1:
            continue

        for row in rows[1:]:
            def get(idx):
                return row[idx].strip() if 0 <= idx < len(row) else ""

            product = get(prod_idx)
            application = get(app_idx)

            if _norm(product).lower() in _SKIP_ROWS:
                continue
            if _norm(application).lower() in _SKIP_ROWS:
                continue
            if re.fullmatch(r"[\d,\s]+", product):  # 합계 금액행
                continue

            results.append({
                "product": product or None,
                "application": application or None,
                "revenue_share": _parse_revenue_value(get(rev_idx)),
            })

    return results


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
