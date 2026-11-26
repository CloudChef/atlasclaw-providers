# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "audit-report" / "scripts"))

from audit_materials import _cell_text, classify_material, read_material  # noqa: E402


def test_filename_classification_gives_ledger_precedence() -> None:
    assert classify_material("检测标准-试验台账.xlsx") == "ledger"
    assert classify_material("检测标准-2024.xlsx") == "standard"
    assert classify_material("补充资料.docx") == "supplement"


def test_zero_padding_preserves_only_integral_non_boolean_values() -> None:
    assert _cell_text(7, "0000") == "0007"
    assert _cell_text(7.0, "0000") == "0007"
    assert _cell_text(1.9, "0000") == "1.9"
    assert _cell_text(True, "0000") == "True"


def test_excel_content_preserves_sheets_positions_and_values(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "检测标准-资料.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "标准"
    sheet.append(["编号", "日期"])
    sheet["A2"] = 123
    sheet["A2"].number_format = "00000"
    sheet["B2"] = datetime(2025, 3, 4)
    other = workbook.create_sheet("附表")
    other.append(["说明", "无损截断"])
    workbook.save(source)

    result = read_material(source)

    assert result["kind"] == "standard"
    assert "标准!A1:B1" in result["content"]
    assert "A2=00123" in result["content"]
    assert "B2=2025-03-04T00:00:00" in result["content"]
    assert "Sheet: 附表" in result["content"]
    assert result["source_position"][1] == {"sheet": "标准", "row": 2, "columns": ["A", "B"]}
    assert len(result["sha256"]) == 64


def test_sparse_excel_row_with_trailing_empty_cells(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "sparse.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"] = "名称"
    sheet["Y1"] = "仪器"
    workbook.save(source)

    result = read_material(source)

    assert "[Sheet!A1:Y1] A1=名称 | Y1=仪器" in result["content"]
    assert result["source_position"] == [{"sheet": "Sheet", "row": 1, "columns": ["A", "Y"]}]


def test_excel_formula_without_cached_value_is_preserved_with_coordinate(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "formula.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"] = "结果"
    sheet["A2"] = "=1+2"
    workbook.save(source)

    result = read_material(source)

    assert "A2==1+2 (cached result unavailable)" in result["content"]
    assert result["source_position"][1] == {"sheet": "Sheet", "row": 2, "columns": ["A"]}


def test_excel_cell_coordinates_use_physical_rows_not_sequence_values(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "row-coordinates.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"] = "序号"
    sheet["C1"] = "设备"
    sheet["F1"] = "日期"
    sheet["A262"] = 7
    sheet["C262"] = "环境试验箱"
    sheet["F262"] = "2025-03-13"
    workbook.save(source)

    result = read_material(source)

    assert "[Sheet!A262:F262] A262=7 | C262=环境试验箱 | F262=2025-03-13" in result["content"]
    assert result["source_position"] == [
        {"sheet": "Sheet", "row": 1, "columns": ["A", "C", "F"]},
        {"sheet": "Sheet", "row": 262, "columns": ["A", "C", "F"]},
    ]
    assert "C7=" not in result["content"] and "F7=" not in result["content"]


def test_empty_excel_is_valid_and_corrupt_excel_reports_filename(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    empty = tmp_path / "empty.xlsx"
    openpyxl.Workbook().save(empty)
    with pytest.raises(ValueError, match="no usable cell values"):
        read_material(empty)

    damaged = tmp_path / "坏台账.xlsx"
    damaged.write_bytes(b"not an xlsx archive")
    with pytest.raises(ValueError, match="坏台账.xlsx"):
        read_material(damaged)


def test_pdf_and_docx_use_existing_extractor_with_positions(tmp_path: Path) -> None:
    fitz = pytest.importorskip("fitz")
    pdf = tmp_path / "检测标准.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Material standard section")
    document.save(pdf)
    document.close()

    pdf_result = read_material(pdf)
    assert "Material standard section" in pdf_result["content"]
    assert pdf_result["source_position"] == [{"page": 1}]

    docx_module = pytest.importorskip("docx")
    docx = tmp_path / "ledger.docx"
    word = docx_module.Document()
    word.add_paragraph("Equipment record")
    table = word.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "ID"
    table.cell(0, 1).text = "0012"
    word.save(docx)

    docx_result = read_material(docx)
    assert "P001 | Equipment record" in docx_result["content"]
    assert "T01-R01 | ID | 0012" in docx_result["content"]
    assert docx_result["source_position"][0]["document"].startswith("DOCX")


def test_text_reader_returns_line_positions(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("line one\nline two\n", encoding="utf-8")
    result = read_material(source)
    assert result["content"] == "line one\nline two\n"
    assert result["source_position"] == [{"line": 1}, {"line": 2}]
