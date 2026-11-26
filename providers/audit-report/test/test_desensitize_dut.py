# -*- coding: utf-8 -*-
"""Regression tests for DUT label handling in sensitive-data redaction."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "audit-report" / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


desensitize_report = _load_script("desensitize_report")
audit_preparation = _load_script("audit_preparation")


def test_dut_alias_requires_an_exact_or_explicit_label_match() -> None:
    assert desensitize_report.is_label("DUT")
    assert desensitize_report.is_label("DUT: sensitive value")
    assert not desensitize_report.is_label("DUT功能正常")
    assert not desensitize_report.is_label("DUT Operating Current")
    assert desensitize_report.is_label("零件名称DUT")
    assert desensitize_report.is_label("委托单位名称")
    assert not desensitize_report.is_label("Specification")
    assert not desensitize_report.is_label("Specification: GB-SECRET")
    assert not desensitize_report.is_label("meet the specifications.")


def test_specification_redaction_does_not_black_out_overlapping_technical_lines(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "desensitized.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 101), "The DUT shall be fully functional before and after the test and all parameters shall", fontsize=11)
    page.insert_text((50, 112), "meet the specifications.", fontsize=11)
    page.insert_text((50, 123), "After the test, the DUT shall be evaluated visually with the naked eye,", fontsize=11)
    doc.save(source)
    doc.close()

    desensitize_report.desensitize_pdf(source, output)

    with pymupdf.open(output) as clean:
        text = clean[0].get_text()
    assert "The DUT shall be fully functional before and after the test and all parameters shall" in text
    assert "meet the specifications." in text
    assert "After the test, the DUT shall be evaluated visually with the naked eye," in text


def test_specification_label_preserves_colon_and_bare_field_values(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "desensitized.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Specification")
    page.insert_text((50, 120), "BARE_PRIVATE_SPEC_VALUE")
    page.insert_text((50, 180), "Specification: COLON_PRIVATE_SPEC_VALUE")
    doc.save(source)
    doc.close()

    desensitize_report.desensitize_pdf(source, output)

    with pymupdf.open(output) as clean:
        text = clean[0].get_text()
    assert "BARE_PRIVATE_SPEC_VALUE" in text
    assert "COLON_PRIVATE_SPEC_VALUE" in text


def test_rand_sensitive_token_does_not_redact_random_technical_terms(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "desensitized.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Broadband random vibration")
    page.insert_text((50, 130), "Rand")
    page.insert_text((50, 160), "冼洋 Rand")
    doc.save(source)
    doc.close()

    desensitize_report.desensitize_pdf(source, output)

    with pymupdf.open(output) as clean:
        text = clean[0].get_text()
    assert "Broadband random vibration" in text
    assert "Rand" in text
    assert "Rand" in text


def test_technical_header_dut_does_not_redact_measurement_values_but_explicit_labels_do(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "desensitized.pdf"
    doc = pymupdf.open()

    technical_page = doc.new_page()
    technical_page.insert_textbox(
        pymupdf.Rect(50, 80, 540, 180),
        "产品端电压  产品工作电流  静态电流  MCU温度\nDUT\n12.5V  35mA  4.2mA  67℃",
        fontname="china-s", fontsize=11,
    )

    private_page = doc.new_page()
    private_page.insert_text((60, 100), "DUT: DUT_PRIVATE_VALUE", fontname="helv", fontsize=11)
    private_page.insert_text((60, 140), "Client Name: COMPANY_PRIVATE_VALUE", fontname="helv", fontsize=11)
    doc.save(source)
    doc.close()

    desensitize_report.desensitize_pdf(source, output)

    with pymupdf.open(output) as clean:
        technical_text = clean[0].get_text()
        private_text = clean[1].get_text()
    assert "12.5V" in technical_text
    assert "35mA" in technical_text
    assert "4.2mA" in technical_text
    assert "67℃" in technical_text
    assert "DUT_PRIVATE_VALUE" not in private_text
    assert "COMPANY_PRIVATE_VALUE" not in private_text


def test_preparation_version_invalidates_old_desensitization_cache() -> None:
    assert audit_preparation.PREPARATION_VERSION == 8


def test_only_confirmed_five_categories_are_sensitive() -> None:
    for label in ("委托单位", "生产单位名称", "Supplier", "联系人", "Applicant address", "OEM", "车型", "项目名称", "Sample Name", "DUT"):
        assert desensitize_report.is_label(label), label
    for label in ("零件号", "样件件号", "批次号", "车型项目号", "Vehicle Project Number", "合同号", "测试计划编号", "Test Plan Approval Number", "软件版本", "硬件版本", "生产日期", "Test phase", "Qty", "材质信息", "Coating information", "Specification", "Test plan", "Supplier Number"):
        assert not desensitize_report.is_label(label), label


def test_pdf_preserves_adjacent_identifiers_and_same_value_elsewhere(tmp_path: Path) -> None:
    source, output = tmp_path / "adjacent.pdf", tmp_path / "clean.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 100), "Client Name")
        page.insert_text((170, 100), "PRIVATE_COMPANY")
        page.insert_text((320, 100), "Part No.")
        page.insert_text((420, 100), "KEEP-PART-001")
        page.insert_text((40, 140), "Project Name: SHARED_VALUE")
        page.insert_text((40, 180), "Report No: SHARED_VALUE")
        page.insert_text((40, 220), "OEM: PRIVATE_OEM   Contract No: KEEP-CONTRACT-001")
        page.insert_text((40, 260), "Material information: TPE LC65A Rand Primer")
        page.insert_text((40, 300), "Test Plan Approval Number: NIO-EE-2024-132")
        pdf.save(source)
    desensitize_report.desensitize_pdf(source, output, tables=True)
    with pymupdf.open(output) as pdf:
        text = pdf[0].get_text()
    for private in ("PRIVATE_COMPANY", "PRIVATE_OEM"):
        assert private not in text
    for retained in ("Part No.", "KEEP-PART-001", "SHARED_VALUE", "KEEP-CONTRACT-001", "TPE LC65A Rand Primer", "NIO-EE-2024-132"):
        assert retained in text, retained


def test_docx_masks_one_value_cell_without_clearing_material_table(tmp_path: Path) -> None:
    from docx import Document
    source, output = tmp_path / "source.docx", tmp_path / "clean.docx"
    document = Document()
    table = document.add_table(rows=3, cols=4)
    for row, values in zip(table.rows, [
        ["项目名称", "PRIVATE_PROJECT", "车型项目号", "KEEP-PROJECT-001"],
        ["表面处理信息", "Primer", "材质信息", "TPE LC65A Rand"],
        ["样品名称Sample Name", "PRIVATE_SAMPLE", "零件号Part No.", "KEEP-PART-001"],
    ]):
        for cell, value in zip(row.cells, values):
            cell.text = value
    document.add_paragraph("OEM: PRIVATE_OEM   Contract No: KEEP-CONTRACT-002")
    document.save(source)
    desensitize_report.desensitize_docx(source, output)
    clean = Document(output)
    text = "\n".join(cell.text for row in clean.tables[0].rows for cell in row.cells)
    assert "PRIVATE_PROJECT" not in text and "PRIVATE_SAMPLE" not in text
    for retained in ("KEEP-PROJECT-001", "Primer", "TPE LC65A Rand", "KEEP-PART-001"):
        assert retained in text, retained
    assert "PRIVATE_OEM" not in clean.paragraphs[0].text
    assert "KEEP-CONTRACT-002" in clean.paragraphs[0].text


def test_oem_word_inside_a_retained_number_is_preserved(tmp_path: Path) -> None:
    source, output = tmp_path / "numbers.pdf", tmp_path / "clean.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 100), "Specification: Xiaomi-STD-2026")
        page.insert_text((40, 140), "OEM: Xiaomi")
        pdf.save(source)
    desensitize_report.desensitize_pdf(source, output)
    with pymupdf.open(output) as pdf:
        text = pdf[0].get_text()
    assert "Xiaomi-STD-2026" in text
    assert text.count("Xiaomi") == 1

    from docx import Document
    source, output = tmp_path / "numbers.docx", tmp_path / "clean.docx"
    doc = Document()
    row = doc.add_table(rows=1, cols=4).rows[0]
    for cell, value in zip(row.cells, ["零件号", "Xiaomi-PART-001", "OEM", "Xiaomi"]):
        cell.text = value
    doc.add_paragraph("Specification: Xiaomi-STD-2026")
    doc.save(source)
    desensitize_report.desensitize_docx(source, output)
    clean = Document(output)
    assert clean.tables[0].cell(0, 1).text == "Xiaomi-PART-001"
    assert clean.tables[0].cell(0, 3).text == "N/A"
    assert "Xiaomi-STD-2026" in clean.paragraphs[0].text


def test_pdf_masks_multiline_value_inside_same_cell_and_keeps_next_cell(tmp_path: Path) -> None:
    source, output = tmp_path / "grid.pdf", tmp_path / "clean.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        for x in (40, 280, 540):
            page.draw_line((x, 60), (x, 220))
        for y in (60, 140, 220):
            page.draw_line((40, y), (540, y))
        page.insert_text((50, 82), "Client Name:")
        page.insert_text((50, 105), "PRIVATE_COMPANY")
        page.insert_text((290, 82), "Part No:")
        page.insert_text((290, 105), "KEEP-PART-001")
        page.insert_text((50, 162), "Material information:")
        page.insert_text((50, 185), "TPE LC65A")
        page.insert_text((290, 162), "Specification:")
        page.insert_text((290, 185), "KEEP-STD-001")
        assert len(page.find_tables().tables) == 1
        pdf.save(source)
    desensitize_report.desensitize_pdf(source, output, tables=True)
    with pymupdf.open(output) as pdf:
        text = pdf[0].get_text()
    assert "PRIVATE_COMPANY" not in text
    for retained in ("KEEP-PART-001", "TPE LC65A", "KEEP-STD-001"):
        assert retained in text


def test_pdf_masks_wrapped_value_lines_at_nearest_column(tmp_path: Path) -> None:
    source, output = tmp_path / "wrapped.pdf", tmp_path / "clean.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 100), "Applicant address:")
        page.insert_text((180, 98), "PRIVATE_ADDRESS_LINE_ONE")
        page.insert_text((180, 110), "PRIVATE_ADDRESS_LINE_TWO")
        page.insert_text((390, 100), "Part No: KEEP-001")
        pdf.save(source)
    desensitize_report.desensitize_pdf(source, output)
    with pymupdf.open(output) as pdf:
        text = pdf[0].get_text()
    assert "PRIVATE_ADDRESS" not in text
    assert "KEEP-001" in text


def test_column_header_redaction_preserves_part_numbers_in_pdf_and_word(tmp_path: Path) -> None:
    from docx import Document
    source, output = tmp_path / "columns.docx", tmp_path / "clean.docx"
    doc = Document()
    table = doc.add_table(rows=3, cols=2)
    values = [["样品名称Sample name", "零件号Part No."], ["PRIVATE_SAMPLE_ONE", "8893495915"], ["PRIVATE_SAMPLE_TWO", "8896072643"]]
    for row, fields in zip(table.rows, values):
        for cell, value in zip(row.cells, fields):
            cell.text = value
    doc.save(source)
    desensitize_report.desensitize_docx(source, output)
    clean = Document(output)
    assert clean.tables[0].cell(1, 0).text == "N/A"
    assert clean.tables[0].cell(2, 0).text == "N/A"
    assert clean.tables[0].cell(1, 1).text == "8893495915"
    assert clean.tables[0].cell(2, 1).text == "8896072643"

    source, output = tmp_path / "columns.pdf", tmp_path / "clean.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        for x in (40, 300, 550):page.draw_line((x, 60), (x, 240))
        for y in (60, 120, 180, 240):page.draw_line((40, y), (550, y))
        for y, fields in zip((90, 150, 210), [["Sample name", "Part No."], values[1], values[2]]):
            page.insert_text((50, y), fields[0]);page.insert_text((310, y), fields[1])
        pdf.save(source)
    desensitize_report.desensitize_pdf(source, output, tables=True)
    with pymupdf.open(output) as pdf:text = pdf[0].get_text()
    assert "PRIVATE_SAMPLE" not in text
    assert "8893495915" in text and "8896072643" in text


def test_signature_pictures_and_typed_names_removed_but_stamp_date_retained(tmp_path: Path) -> None:
    import io
    from PIL import Image
    from docx import Document
    def picture(color):
        buffer = io.BytesIO()
        Image.new("RGB", (20, 20), color).save(buffer, format="PNG")
        return buffer.getvalue()
    source, output = tmp_path / "signatures.pdf", tmp_path / "clean.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        for x in (40, 200, 360, 540):page.draw_line((x, 60), (x, 170))
        for y in (60, 100, 170):page.draw_line((40, y), (540, y))
        for x, label in [(50, "Prepare"), (210, "Audit"), (370, "Issue Date")]:
            page.insert_text((x, 85), label)
        page.insert_image(pymupdf.Rect(60, 112, 120, 155), stream=picture("red"))
        page.insert_image(pymupdf.Rect(220, 108, 310, 195), stream=picture("blue"))
        page.insert_text((220, 130), "PRIVATE_SIGNER")
        page.insert_text((380, 135), "2025-03-28")
        page.insert_image(pymupdf.Rect(225, 185, 320, 250), stream=picture("green"))
        page.insert_text((40, 290), "The report requires signatures and a seal.")
        pdf.save(source)
    desensitize_report.desensitize_pdf(source, output, tables=True)
    with pymupdf.open(output) as pdf:
        page = pdf[0]
        assert "PRIVATE_SIGNER" not in page.get_text()
        assert "2025-03-28" in page.get_text()
        assert "requires signatures and a seal" in page.get_text()
        boxes = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
        assert not any(box.contains(pymupdf.Point(80, 130)) or box.contains(pymupdf.Point(250, 130)) for box in boxes)
        assert any(box.contains(pymupdf.Point(250, 220)) for box in boxes)

    source, output = tmp_path / "signatures.docx", tmp_path / "clean.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=3)
    for cell, label in zip(table.rows[0].cells, ["编制/ Prepare", "审核/ Audit", "签发日期/ Issue Date"]):cell.text = label
    table.cell(1, 0).paragraphs[0].add_run().add_picture(io.BytesIO(picture("red")))
    table.cell(1, 1).text = "PRIVATE_SIGNER"
    table.cell(1, 2).text = "2025-03-28"
    doc.add_picture(io.BytesIO(picture("green")))
    doc.save(source)
    desensitize_report.desensitize_docx(source, output)
    clean = Document(output)
    assert not list(clean.tables[0].cell(1, 0)._tc.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"))
    assert "PRIVATE_SIGNER" not in clean.tables[0].cell(1, 1).text
    assert clean.tables[0].cell(1, 2).text == "2025-03-28"
    assert len(clean.inline_shapes) == 1


def test_signature_widgets_are_deleted_without_deleting_seal_widgets(tmp_path: Path) -> None:
    source, output = tmp_path / "widgets.pdf", tmp_path / "clean.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        for x in (40, 220, 440):page.draw_line((x, 60), (x, 180))
        for y in (60, 110, 180):page.draw_line((40, y), (440, y))
        page.insert_text((60, 90), "Prepare")
        page.insert_text((240, 90), "Issue Date")
        page.insert_text((240, 150), "2025-03-28")
        for name, rect in [("WRITE_SIGN-private", pymupdf.Rect(60, 120, 180, 170)), ("SEAL_SIGN-preserve", pymupdf.Rect(100, 230, 230, 320))]:
            widget = pymupdf.Widget()
            widget.field_name = name
            widget.field_type = pymupdf.PDF_WIDGET_TYPE_SIGNATURE
            widget.rect = rect
            page.add_widget(widget)
        pdf.save(source)
    desensitize_report.desensitize_pdf(source, output)
    with pymupdf.open(output) as pdf:
        names = [widget.field_name for widget in pdf[0].widgets() or []]
        assert "WRITE_SIGN-private" not in names
        assert names == ["SEAL_SIGN-preserve"]
        assert "2025-03-28" in pdf[0].get_text()
