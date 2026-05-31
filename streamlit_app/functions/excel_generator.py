import io
from openpyxl import Workbook
from openpyxl.styles import (
    PatternFill, Font, Alignment, Border, Side
)
from openpyxl.utils import get_column_letter

# 색상
YELLOW      = "FFFF00"
LIGHT_YELLOW = "FFFACD"
BLUE        = "4472C4"
WHITE       = "FFFFFF"
LIGHT_GRAY  = "F2F2F2"
NAVY        = "1B3A6B"

_thin = Side(style="thin", color="CCCCCC")
_border = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)


def _fill(hex_color: str) -> PatternFill:
    return PatternFill(fill_type="solid", fgColor=hex_color)


def _font(bold=False, italic=False, color=None, size=11) -> Font:
    return Font(bold=bold, italic=italic, color=color or "000000", size=size)


def _align(wrap=True, indent=0) -> Alignment:
    return Alignment(wrap_text=wrap, vertical="center", indent=indent)


def _build_sheet1(wb: Workbook, deck_structure: list[dict], query: str):
    ws = wb.active
    ws.title = "덱 구성"

    # 열 너비
    ws.column_dimensions["A"].width = 6   # Section 번호
    ws.column_dimensions["B"].width = 8   # 장 번호
    ws.column_dimensions["C"].width = 30  # 제목
    ws.column_dimensions["D"].width = 60  # 설명/핵심메시지

    # 헤더 행
    ws.row_dimensions[1].height = 22
    for col, text in enumerate(["Section", "장", "제목", "내용/핵심메시지"], start=1):
        cell = ws.cell(row=1, column=col, value=text)
        cell.fill = _fill(NAVY)
        cell.font = _font(bold=True, color=WHITE, size=11)
        cell.alignment = _align()
        cell.border = _border

    row = 2
    for sec in deck_structure:
        sec_no = sec.get("section_no", "")
        sec_title = sec.get("section_title", "")
        label = f"Section {sec_no}: {sec_title}"

        # Section 헤더 행 (노란색, 4열 병합)
        ws.row_dimensions[row].height = 20
        ws.merge_cells(f"A{row}:D{row}")
        cell = ws.cell(row=row, column=1, value=label)
        cell.fill = _fill(YELLOW)
        cell.font = _font(bold=True, size=11)
        cell.alignment = _align()
        cell.border = _border
        row += 1

        # 장 행
        for ch in sec.get("chapters", []):
            ws.row_dimensions[row].height = 40
            ws.cell(row=row, column=1, value="").border = _border
            ws.cell(row=row, column=2, value=f"장 {ch.get('no', '')}").border = _border
            ws.cell(row=row, column=2).alignment = _align()

            title_cell = ws.cell(row=row, column=3, value=ch.get("title", ""))
            title_cell.alignment = _align(indent=1)
            title_cell.border = _border

            desc_cell = ws.cell(row=row, column=4, value=ch.get("description", ""))
            desc_cell.alignment = _align()
            desc_cell.border = _border
            row += 1

        # 핵심 메시지 행 (연한 노란색, 이탤릭)
        ws.row_dimensions[row].height = 20
        ws.merge_cells(f"A{row}:D{row}")
        cell = ws.cell(row=row, column=1, value=sec.get("key_message", ""))
        cell.fill = _fill(LIGHT_YELLOW)
        cell.font = _font(italic=True, size=10)
        cell.alignment = _align()
        cell.border = _border
        row += 1

        # 빈 행 간격
        row += 1


def _build_sheet2(wb: Workbook, research_data: list[dict], data_limitations: list[str]):
    ws = wb.create_sheet(title="리서치 데이터")

    ws.column_dimensions["A"].width = 40  # 항목
    ws.column_dimensions["B"].width = 40  # 데이터/수치
    ws.column_dimensions["C"].width = 30  # 출처

    # 헤더 행
    ws.row_dimensions[1].height = 22
    for col, text in enumerate(["항목", "데이터/수치 (신고서 원문)", "출처"], start=1):
        cell = ws.cell(row=1, column=col, value=text)
        cell.fill = _fill(NAVY)
        cell.font = _font(bold=True, color=WHITE, size=11)
        cell.alignment = _align()
        cell.border = _border

    row = 2
    for topic_block in research_data:
        topic = topic_block.get("topic", "")

        # 토픽 헤더 행 (파란색, 3열 병합)
        ws.row_dimensions[row].height = 20
        ws.merge_cells(f"A{row}:C{row}")
        cell = ws.cell(row=row, column=1, value=topic)
        cell.fill = _fill(BLUE)
        cell.font = _font(bold=True, color=WHITE, size=11)
        cell.alignment = _align()
        cell.border = _border
        row += 1

        for item in topic_block.get("items", []):
            ws.row_dimensions[row].height = 35

            text_cell = ws.cell(row=row, column=1, value=item.get("text", ""))
            text_cell.alignment = _align()
            text_cell.border = _border

            data_cell = ws.cell(row=row, column=2, value=item.get("data", ""))
            data_cell.alignment = _align()
            data_cell.border = _border

            src_cell = ws.cell(row=row, column=3, value=item.get("source", ""))
            src_cell.alignment = _align()
            src_cell.font = _font(color="1B3A6B", size=10)
            src_cell.border = _border
            row += 1

        row += 1  # 토픽 간 간격

    # 데이터 한계 섹션
    if data_limitations:
        row += 1
        ws.merge_cells(f"A{row}:C{row}")
        cell = ws.cell(row=row, column=1, value="⚠ 데이터 한계 및 유의사항")
        cell.fill = _fill("FFF3CD")
        cell.font = _font(bold=True, size=11)
        cell.border = _border
        row += 1

        for limit in data_limitations:
            ws.merge_cells(f"A{row}:C{row}")
            cell = ws.cell(row=row, column=1, value=f"• {limit}")
            cell.alignment = _align()
            cell.border = _border
            row += 1


def generate_excel(analysis: dict, query: str, analysis_date: str) -> bytes:
    """
    analysis: analysis_agent.run() 출력 JSON
    반환: xlsx 파일 bytes
    """
    wb = Workbook()

    _build_sheet1(wb, analysis.get("deck_structure", []), query)
    _build_sheet2(wb, analysis.get("research_data", []), analysis.get("data_limitations", []))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
