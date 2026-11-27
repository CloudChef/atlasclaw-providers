# -*- coding: utf-8 -*-
"""Local report delivery tests using synthetic Markdown and PDF inputs."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "audit-report" / "scripts" / "audit_delivery.py"
spec = importlib.util.spec_from_file_location("audit_delivery", SCRIPT)
audit_delivery = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit_delivery)


def _source_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "封面编号 JC-2026-001", fontname="china-s", fontsize=14)
    page = doc.new_page()
    page.insert_text((72, 100), "检测数据：温升 25℃", fontname="china-s", fontsize=14)
    doc.save(path)
    doc.close()
    return path


def test_audit_delivery_loads_by_file_spec_in_fresh_interpreter(tmp_path: Path):
    code = f"""
import importlib.util
from pathlib import Path
script = Path({str(SCRIPT)!r})
spec = importlib.util.spec_from_file_location('standalone_audit_delivery', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert callable(module._pdf_css)
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code], cwd=tmp_path,
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr


def test_pdf_stylesheet_rejects_unknown_template_placeholders(monkeypatch):
    monkeypatch.setattr(audit_delivery, "load_template", lambda _name: "$font_css $unknown")
    with pytest.raises(KeyError, match="unknown"):
        audit_delivery._pdf_css("body {font-family: test;}")


def test_pdf_css_suppresses_repeated_story_backgrounds_and_fixes_field_columns(
    tmp_path: Path,
) -> None:
    report_css = (SCRIPT.parent.parent / "references" / "report" / "report.css").read_text(
        encoding="utf-8"
    )
    field_value = (
        "FIELD_VALUE report 2025-06-17; register 2027-06-14; all source text "
        "must remain visible in this report cell"
    )
    html = f'''<!doctype html>
<html><head><meta charset="utf-8"><style>{report_css}</style></head>
<body><main class="page">
<p class="verdict verdict-fail">Summary outcome</p>
<div class="table-wrap"><table><thead><tr><th>Grade</th><th>Count</th><th>Rules</th></tr></thead>
<tbody>
<tr><td><span class="sev sev-a">A severe</span></td><td>2</td><td>R01, R02</td></tr>
<tr><td><span class="sev sev-b">B major</span></td><td>3</td><td>R03, R04, R05</td></tr>
<tr><td><span class="sev sev-c">C minor</span></td><td>1</td><td>R06</td></tr>
</tbody></table></div>
<section class="check-point finding-point"><h3>F-TEST-001 · Finding</h3>
<table class="field-table"><colgroup><col width="22%"><col width="78%"></colgroup><tbody>
<tr><th scope="row" width="22%" style="width:22%">FIELD_LABEL</th>
<td width="78%" style="width:78%">{field_value}</td></tr>
</tbody></table></section>
</main></body></html>'''
    html_path = tmp_path / "fragmented-table.html"
    pdf_path = tmp_path / "fragmented-table.pdf"
    html_path.write_text(html, encoding="utf-8")

    audit_delivery._render_pdf(html_path, pdf_path)

    with pymupdf.open(pdf_path) as document:
        field_page = next(page for page in document if "FIELD_LABEL" in page.get_text())
        page_text = re.sub(r"\s+", " ", field_page.get_text().replace("\xa0", " "))
        assert field_value in page_text
        broad_fills = [
            drawing
            for drawing in field_page.get_drawings()
            if drawing.get("fill")
            and drawing["rect"].width > 1.5
            and drawing["rect"].height > 1.5
        ]
        assert not broad_fills
        label = field_page.search_for("FIELD_LABEL")[0]
        value = field_page.search_for("FIELD_VALUE")[0]
        assert 110 < value.x0 - label.x0 < 120


def test_pdf_object_table_keeps_full_sha256_inside_readable_columns(tmp_path: Path) -> None:
    report_css = (SCRIPT.parent.parent / "references" / "report" / "report.css").read_text(
        encoding="utf-8"
    )
    sha256 = "6f1ac04180c2d21af2d3df8583dab6917ca1608c9de90e89c2d746a1a90bd54d"
    html = f'''<!doctype html>
<html><head><meta charset="utf-8"><style>{report_css}</style></head>
<body><main class="page"><h2>1. 审核对象</h2>
<div class="table-wrap"><table><thead><tr><th>项目</th><th>内容</th></tr></thead>
<tbody><tr><td>文件名</td><td><code>example.pdf</code></td></tr>
<tr><td>SHA-256</td><td><code>{sha256}</code></td></tr>
<tr><td>报告编号</td><td><code>GDTSQ2504004A03</code></td></tr>
<tr><td>检测状态</td><td>原始文本中的委托单位和其他字段信息完整保留。</td></tr>
</tbody></table></div></main></body></html>'''
    html_path = tmp_path / "object-table.html"
    pdf_path = tmp_path / "object-table.pdf"
    html_path.write_text(html, encoding="utf-8")

    audit_delivery._render_pdf(html_path, pdf_path)

    with pymupdf.open(pdf_path) as document:
        page = document[0]
        normalized = re.sub(r"\s+", "", page.get_text())
        assert sha256 in normalized
        assert "原始文本中的委托单位和其他字段信息完整保留。" in page.get_text()
        label = page.search_for("SHA-256")[0]
        hash_start = page.search_for(sha256[:8])[0]
        assert 100 < hash_start.x0 - label.x0 < 125
        assert all(word[2] <= 553.28 for word in page.get_text("words"))


def _finding(fid: str, page: str, quote: str, rule: str = "R05") -> str:
    return f"""### {fid} [A] 标识问题（{rule}）

- **规则号**：`{rule}`
- **页码**：第 {page} 页
- **原文上下文**：
  - 前文：「无关上下文」
  - 问题处：「{quote}」
- **不规范说明**：模型给出的原始结论。
- **证据截图**：

![原模型说明](evidence/{fid}.png)
"""


def test_deliver_report_captures_same_rule_findings_and_preserves_raw_markdown(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.md"
    raw = "# 审核报告\n\n## 5. 检查覆盖表\n\n| # | 结果 |\n|---|---|\n| R05 | 不通过 |\n\n" + _finding("F-01", "1", "封面编号 JC-2026-001") + "\n" + _finding("F-02", "2", "检测数据：温升 25℃")
    raw_path.write_text(raw, encoding="utf-8")
    pdf = _source_pdf(tmp_path / "source.pdf")

    result = audit_delivery.deliver_report(raw_path, pdf, tmp_path / "report.pdf")

    assert raw_path.read_text(encoding="utf-8") == raw
    assert [item["status"] for item in result["findings"]] == ["captured", "captured"]
    assert (tmp_path / "evidence" / "F-01.png").is_file()
    assert (tmp_path / "evidence" / "F-02.png").is_file()
    enriched = Path(result["enriched_markdown"]).read_text(encoding="utf-8")
    assert "检查覆盖表" in enriched
    assert "evidence/F-01.png" in enriched and "evidence/F-02.png" in enriched
    delivered = pymupdf.open(result["pdf"])
    text = "\n".join(page.get_text() for page in delivered)
    assert "检测数据" in text
    assert "不通过" in text
    assert "audit-report 技能生成" not in text
    assert delivered.page_count >= 1
    assert sum(len(page.get_images(full=True)) for page in delivered) >= 2
    assert any(re.search(r"\b\d+ / \d+\b", page.get_text()) for page in delivered)


def test_bold_global_finding_headings_are_captured_and_rendered(tmp_path: Path) -> None:
    raw = tmp_path / "raw.md"
    raw.write_text(
        "# Audit\n\n"
        "**F-000-001 [A] First global finding**\n"
        "- **页码**：第 1 页\n- **原文上下文**：封面编号 JC-2026-001\n\n"
        "**F-000-002 [B] Second global finding**\n"
        "- **页码**：第 2 页\n- **原文上下文**：检测数据：温升 25℃\n",
        encoding="utf-8",
    )

    result = audit_delivery.deliver_report(raw, _source_pdf(tmp_path / "source.pdf"), tmp_path / "report.pdf")

    assert [item["id"] for item in result["findings"]] == ["F-000-001", "F-000-002"]
    assert all(item["status"] == "captured" for item in result["findings"])
    assert all(item["images"] for item in result["findings"])
    enriched = Path(result["enriched_markdown"]).read_text(encoding="utf-8")
    assert "### F-000-001 [A] First global finding" in enriched
    assert "### F-000-002 [B] Second global finding" in enriched
    assert result["evidence_errors"] == []


def test_missing_safe_evidence_reference_is_a_delivery_error(tmp_path: Path) -> None:
    raw = tmp_path / "raw.md"
    raw.write_text(
        "# Report\n\n" + _finding("F-01", "1", "封面编号 JC-2026-001")
        + "\n![Missing finding](evidence/F-999-001.png)\n",
        encoding="utf-8",
    )

    result = audit_delivery.deliver_report(raw, _source_pdf(tmp_path / "source.pdf"), tmp_path / "report.pdf")

    assert any("evidence/F-999-001.png" in item for item in result["errors"])
    assert any("evidence/F-999-001.png" in item for item in result["evidence_errors"])


def test_invalid_page_gets_technical_error_and_keeps_model_verdict(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.md"
    raw = "# 审核报告\n\n**总评：不通过**\n\n" + _finding("F-01", "99", "封面编号 JC-2026-001")
    raw_path.write_text(raw, encoding="utf-8")
    pdf = _source_pdf(tmp_path / "source.pdf")

    result = audit_delivery.deliver_report(raw_path, pdf, tmp_path / "report.pdf")

    assert result["findings"][0]["status"] == "error"
    enriched = Path(result["enriched_markdown"]).read_text(encoding="utf-8")
    assert "本地证据处理错误" in enriched
    assert "**总评：不通过**" in enriched
    assert "模型审核结论保持原样" in enriched
    assert result["pdf"] is not None


def test_external_image_reference_is_not_read_or_rendered(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.md"
    raw_path.write_text("# 报告\n\n![外部](../secret.png)\n", encoding="utf-8")
    pdf = _source_pdf(tmp_path / "source.pdf")

    result = audit_delivery.deliver_report(raw_path, pdf, tmp_path / "report.pdf")

    enriched = Path(result["enriched_markdown"]).read_text(encoding="utf-8")
    assert "../secret.png" not in enriched
    assert "忽略不安全的本地图片引用" in enriched
    assert result["pdf"] is not None


def test_failed_finding_edit_does_not_shift_later_blocks(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.md"
    raw = "# Report\n\n" + _finding("F-01", "99", "not on this page") + "\n" + _finding("F-02", "2", "检测数据：温升 25℃")
    raw_path.write_text(raw, encoding="utf-8")
    pdf = _source_pdf(tmp_path / "source.pdf")

    result = audit_delivery.deliver_report(raw_path, pdf, tmp_path / "report.pdf")

    enriched = Path(result["markdown"]).read_text(encoding="utf-8")
    assert "### F-01 [A] 标识问题" in enriched
    assert "### F-02 [A] 标识问题" in enriched
    assert "不规范说明**：模型给出的原始结论。" in enriched
    assert "evidence/F-02.png" in enriched
    assert [finding["status"] for finding in result["findings"]] == ["error", "captured"]


def test_valid_page_with_unmatched_context_uses_full_page_capture(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.md"
    raw_path.write_text("# Report\n\n" + _finding("F-01", "1", "不存在于页面的引用"), encoding="utf-8")
    pdf = _source_pdf(tmp_path / "source.pdf")

    result = audit_delivery.deliver_report(raw_path, pdf, tmp_path / "report.pdf")

    assert result["findings"][0]["status"] == "captured"
    assert result["findings"][0]["capture_mode"] == "full-page fallback"
    assert (tmp_path / "evidence" / "F-01.png").is_file()


def test_mult_page_finding_captures_every_page_and_inline_context(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.md"
    block = _finding("F-01", "1", "封面编号 JC-2026-001")
    block = block.replace("第 1 页", "第 1; 2 页")
    block = re.sub(
        r"- \*\*原文上下文\*\*：[\s\S]*?- \*\*不规范说明\*\*：",
        "- **原文上下文**：封面编号 JC-2026-001\n- **不规范说明**：",
        block,
    )
    raw = "# Report\n\n" + block
    raw_path.write_text(raw, encoding="utf-8")
    pdf = _source_pdf(tmp_path / "source.pdf")

    result = audit_delivery.deliver_report(raw_path, pdf, tmp_path / "report.pdf")

    finding = result["findings"][0]
    assert finding["status"] == "captured"
    assert finding["page"] == 1
    assert [image["page"] for image in finding["images"]] == [1, 2]
    assert (tmp_path / "evidence" / "F-01.png").is_file()
    assert (tmp_path / "evidence" / "F-01-p1.png").is_file()
    assert (tmp_path / "evidence" / "F-01-p2.png").is_file()
    assert finding["images"][1]["capture_mode"] == "full-page fallback"
    enriched = Path(result["enriched_markdown"]).read_text(encoding="utf-8")
    assert "evidence/F-01.png" in enriched
    assert "evidence/F-01-p2.png" in enriched
    with pymupdf.open(result["report_pdf"]) as delivered:
        assert sum(len(page.get_images(full=True)) for page in delivered) >= 2
    assert raw_path.read_text(encoding="utf-8") == raw


def test_explicit_pages_expand_ranges_and_invalid_page_does_not_make_image(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.md"
    block = _finding("F-01", "1", "封面编号 JC-2026-001")
    block = block.replace("第 1 页", "第 1-2; 99 页")
    raw_path.write_text("# Report\n\n" + block, encoding="utf-8")
    result = audit_delivery.deliver_report(
        raw_path, _source_pdf(tmp_path / "source.pdf"), tmp_path / "report.pdf"
    )

    finding = result["findings"][0]
    assert finding["status"] == "error"
    assert [image["page"] for image in finding["images"]] == [1, 2]
    assert "页码 99 超出" in finding["error"]
    assert (tmp_path / "evidence" / "F-01-p1.png").is_file()
    assert (tmp_path / "evidence" / "F-01-p2.png").is_file()
    assert not (tmp_path / "evidence" / "F-01-p99.png").exists()


def test_continuation_captures_previous_page_but_keeps_cited_page_as_legacy_image(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.md"
    raw_path.write_text(
        "# Report\n\n" + _finding("F-01", "2", "检测数据：温升 25℃") + "\n本条为跨页续表。\n",
        encoding="utf-8",
    )
    result = audit_delivery.deliver_report(
        raw_path, _source_pdf(tmp_path / "source.pdf"), tmp_path / "report.pdf"
    )

    finding = result["findings"][0]
    assert [image["page"] for image in finding["images"]] == [1, 2]
    assert finding["images"][0]["context_page"] is True
    assert finding["images"][1]["context_page"] is False
    assert (tmp_path / "evidence" / "F-01.png").read_bytes() == (
        tmp_path / "evidence" / "F-01-p2.png"
    ).read_bytes()


def test_project_issue_namespace_is_captured_without_truncation(tmp_path: Path) -> None:
    raw = tmp_path / "raw.md"
    raw.write_text("# Report\n\n" + _finding("F-1000-1001", "1", "封面编号 JC-2026-001") +
                   "\n" + _finding("F-000-1000", "2", "检测数据：温升 25℃"), encoding="utf-8")
    result = audit_delivery.deliver_report(raw, _source_pdf(tmp_path / "source.pdf"), tmp_path / "report.pdf")

    assert [item["id"] for item in result["findings"]] == ["F-1000-1001", "F-000-1000"]
    assert all(item["status"] == "captured" for item in result["findings"])
    assert (tmp_path / "evidence" / "F-1000-1001.png").is_file()
    assert (tmp_path / "evidence" / "F-000-1000.png").is_file()
    enriched = Path(result["enriched_markdown"]).read_text(encoding="utf-8")
    assert "### F-1000-1001" in enriched and "### F-000-1000" in enriched


def test_render_failure_does_not_report_existing_output_as_success(tmp_path: Path, monkeypatch) -> None:
    raw_path = tmp_path / "raw.md"
    raw_path.write_text("# Report\n", encoding="utf-8")
    pdf = _source_pdf(tmp_path / "source.pdf")
    output = tmp_path / "report.pdf"
    output.write_bytes(b"old output")

    monkeypatch.setattr(audit_delivery.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=1, stdout="", stderr="synthetic renderer failure"))
    result = audit_delivery.deliver_report(raw_path, pdf, output)

    assert result["report_pdf"] is None
    assert result["pdf"] is None
    assert output.read_bytes() == b"old output"
    assert any("synthetic renderer failure" in error for error in result["errors"])


def test_delivery_subprocesses_add_no_fixed_timeout(tmp_path: Path, monkeypatch) -> None:
    raw_path = tmp_path / "raw.md"
    raw_path.write_text("# Report\n\n" + _finding("F-01", "1", "封面编号 JC-2026-001"), encoding="utf-8")
    pdf = _source_pdf(tmp_path / "source.pdf")
    original_run = subprocess.run
    calls = []

    def inspect_run(command, **kwargs):
        assert "timeout" not in kwargs
        calls.append(command)
        return original_run(command, **kwargs)

    monkeypatch.setattr(audit_delivery.subprocess, "run", inspect_run)
    result = audit_delivery.deliver_report(raw_path, pdf, tmp_path / "report.pdf")

    assert len(calls) >= 2  # Evidence capture and HTML rendering.
    assert result["pdf"] is not None


def test_duplicate_finding_ids_cannot_overwrite_evidence(tmp_path: Path) -> None:
    raw = tmp_path / "raw.md"
    raw.write_text("# Report\n\n" + _finding("F-01", "1", "封面编号") + _finding("F-01", "2", "检测数据"), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate finding"):
        audit_delivery.deliver_report(raw, _source_pdf(tmp_path / "source.pdf"), tmp_path / "report.pdf")
    assert not list((tmp_path / "evidence").glob("*.png"))


def test_page_lists_use_first_physical_page_and_finding_references_are_not_pages():
    block = _finding("F-01", "33, 44, 55", "example context")
    assert audit_delivery._finding_context(block)[0] == 33
    assert audit_delivery._finding_context_data(block)[0] == [(33, 33), (44, 44), (55, 55)]
    assert audit_delivery._finding_context(block.replace("第 33, 44, 55 页", "全文（第 1–472 页）"))[0] == 1
    assert audit_delivery._finding_context(block.replace("第 33, 44, 55 页", "同 F-03 所列照片页"))[0] is None


def test_single_line_and_plain_paragraph_context_are_read_as_quotes() -> None:
    single_line = "### F-01 issue\n- **原文上下文**：表头：报告编号 | 检测结果\n- **页码**：第 8 页"
    paragraph = "### F-02 issue\n- **原文上下文**：\n原文：『设备编号：0008』\n- **页码**：第 9 页"
    assert audit_delivery._finding_context(single_line)[1] == "表头：报告编号 | 检测结果"
    assert audit_delivery._finding_context(paragraph)[1] == "设备编号：0008"


def test_fenced_source_context_skips_fences_and_keeps_negative_values_and_bold_labels() -> None:
    block = """### F-01 [A] 问题（R05）
- **页码**：第 1 页
- **原文上下文**：
  ```text
  | **测量字段** | 温度 |
- **字段**：原值
- **问题处**：样品 | CH3 | -40℃ | -1.0
  ```
- **不规范说明**：结论。
"""
    intervals, quote = audit_delivery._finding_context_data(block)
    assert intervals == [(1, 1)]
    assert quote == "样品 | CH3 | -40℃ | -1.0"


def test_nested_context_labels_do_not_end_context_field() -> None:
    block = """### F-01 [A] 问题（R05）
- **页码**：第 1 页
- **原文上下文**：
  - **前文**：上一行数据
  - **问题处**：样品 | CH3 | -40℃
  - **后文**：下一行数据
- **判定依据**：规则要求范围内
- **不规范说明**：结论。
"""
    assert audit_delivery._finding_context_data(block)[1] == "样品 | CH3 | -40℃"
    assert audit_delivery._context_source_lines(block) == [
        "- **前文**：上一行数据",
        "- **问题处**：样品 | CH3 | -40℃",
        "- **后文**：下一行数据",
    ]


def test_context_parser_handles_nine_fenced_problem_blocks_without_external_artifacts() -> None:
    blocks = [
        f"""### F-{index:02d} [A] 问题（R05）
- **页码**：第 1 页
- **原文上下文**：
  ```markdown
- **字段**：原值
- **问题处**：样品 {index:02d} | CH3 | -40℃ | -1.0
  ```
- **不规范说明**：结论。
"""
        for index in range(1, 10)
    ]
    parsed = [audit_delivery._finding_context_data(block)[1] for block in blocks]
    assert parsed == [f"样品 {index:02d} | CH3 | -40℃ | -1.0" for index in range(1, 10)]


def test_single_character_context_quote_is_not_rejected() -> None:
    block = "### F-01 issue\n- **原文上下文**：A\n- **页码**：第 1 页"
    assert audit_delivery._finding_context_data(block)[1] == "A"


def test_empty_context_field_stays_missing() -> None:
    block = "### F-01 issue\n- **原文上下文**：\n- **页码**：第 1 页"
    assert audit_delivery._finding_context_data(block)[1] is None


@pytest.mark.parametrize("context_reference", [
    "同 F-01 所列原文上下文。",
    "同 F-01所列原文上下文。",
])
def test_explicit_finding_references_reuse_known_page_and_context(
    tmp_path: Path, context_reference: str, monkeypatch,
) -> None:
    original_run = audit_delivery.subprocess.run
    searches = []

    def record_capture_search(command, *args, **kwargs):
        if isinstance(command, list) and any(str(part).endswith("capture_evidence.py") for part in command):
            searches.append(command[command.index("--search") + 1])
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(audit_delivery.subprocess, "run", record_capture_search)
    raw = tmp_path / "raw.md"
    second = _finding("F-02", "2", "unused").replace("第 2 页", "同 F-01 所列页码")
    second = second.replace("  - 前文：「无关上下文」\n  - 问题处：「unused」", context_reference)
    raw.write_text("# Report\n\n" + _finding("F-01", "1", "封面编号 JC-2026-001") + second, encoding="utf-8")
    result = audit_delivery.deliver_report(raw, _source_pdf(tmp_path / "source.pdf"), tmp_path / "report.pdf")
    assert [(item["page"], item["status"]) for item in result["findings"]] == [(1, "captured"), (1, "captured")]
    assert result["findings"][1]["images"][0]["capture_mode"] == "quote"
    assert searches == ["封面编号 JC-2026-001", "封面编号 JC-2026-001"]


def test_cyclic_finding_references_fail_closed(tmp_path: Path) -> None:
    first = _finding("F-01", "1", "unused").replace("第 1 页", "同 F-02 所列页码")
    first = first.replace("  - 前文：「无关上下文」\n  - 问题处：「unused」", "同 F-02所列原文上下文。")
    second = _finding("F-02", "2", "unused").replace("第 2 页", "同 F-01 所列页码")
    second = second.replace("  - 前文：「无关上下文」\n  - 问题处：「unused」", "同 F-01所列原文上下文。")
    raw = tmp_path / "raw.md"
    raw.write_text("# Report\n\n" + first + second, encoding="utf-8")

    result = audit_delivery.deliver_report(raw, _source_pdf(tmp_path / "source.pdf"), tmp_path / "report.pdf")

    assert [item["status"] for item in result["findings"]] == ["error", "error"]
    assert all(not item["images"] for item in result["findings"])


def test_wide_table_last_columns_remain_visible_in_pdf(tmp_path: Path) -> None:
    raw = tmp_path / "raw.md"
    raw.write_text("# Report\n\n| A | B | C | D | E | F | G | H |\n|---|---|---|---|---|---|---|---|\n"
                   "| record | device | name | model | date | source | verdict | LAST_COLUMN_VISIBLE |\n", encoding="utf-8")
    result = audit_delivery.deliver_report(raw, _source_pdf(tmp_path / "source.pdf"), tmp_path / "report.pdf")
    with pymupdf.open(result["report_pdf"]) as pdf:
        assert "LAST_COLUMN_VISIBLE" in "\n".join(page.get_text() for page in pdf)
        for page in pdf:
            for word in page.get_text("words"):
                assert word[2] <= page.rect.width - 20


def test_main_finding_table_and_real_screenshot_are_on_same_pdf_page(tmp_path: Path):
    source = tmp_path / "raw.md"
    raw = (
        "# 审核报告\n\n## 问题清单\n"
        "| 序号/FID | 规则号 | 复核结果 | 最终等级 | 页码 | 位置 | 问题摘要 | 理由/依据 | 规则来源 |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| F-001-001 | R05 | 成立 | A | 第1页 | 封面 | 最终问题 | 模型最终复核依据 | 内置 |\n\n"
        "# 附录：分项目审核原文\n\n" + _finding("F-001-001", "1", "封面编号 JC-2026-001")
    )
    source.write_text(raw, encoding="utf-8")
    result = audit_delivery.deliver_report(source, _source_pdf(tmp_path / "source.pdf"), tmp_path / "report.pdf")
    assert result["errors"] == []
    html = Path(result["html"]).read_text(encoding="utf-8")
    assert 'src="data:image/png;base64,' in html.split("附录：分项目审核原文")[0]
    with pymupdf.open(result["pdf"]) as pdf:
        assert any("最终问题" in page.get_text() and page.get_images() for page in pdf)
    assert source.read_text(encoding="utf-8") == raw


def test_capture_contains_every_fragment_of_wrapped_quote(tmp_path: Path):
    import json
    import sys
    source = tmp_path / "wrapped.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((240, 100), "first quoted line", fontsize=14)
        page.insert_text((72, 125), "second quoted line", fontsize=14)
        quote = "first quoted line second quoted line"
        hits = page.search_for(quote)
        assert len(hits) == 2
        document.save(source)
    target = tmp_path / "quote.png"
    result = subprocess.run([sys.executable, str(SCRIPT.parent / "capture_evidence.py"), str(source),
                             "--page", "1", "--search", quote, "--above", "0", "--below", "0", "--out", str(target)],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    metadata = json.loads(target.with_suffix(".png.json").read_text(encoding="utf-8"))
    clip = pymupdf.Rect(metadata["clip"])
    for hit in hits:
        assert clip.x0 <= hit.x0 and clip.x1 >= hit.x1
        assert clip.y0 <= round(hit.y0, 2) and clip.y1 >= round(hit.y1, 2)


@pytest.mark.parametrize("annotation", ["（各项目同构，摘原文）", "（代表性原文）", "(source excerpt)"])
def test_context_field_accepts_explanatory_label_suffix_and_source_page_prefix(annotation: str) -> None:
    block = (
        "### F-000-001 [B] 标准引用问题（R07）\n"
        "- **页码**：第 6 页\n"
        f"- **原文上下文**{annotation}：\n"
        "  - 第 6 页：「检测标准Test Standards: 客户要求 Customer requirements」\n"
        "- **不规范说明**：模型原始判断。\n"
    )
    intervals, quote = audit_delivery._finding_context_data(block)
    assert intervals == [(6, 6)]
    assert quote == "检测标准Test Standards: 客户要求 Customer requirements"
