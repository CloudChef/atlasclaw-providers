from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "audit-report" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import render_report  # noqa: E402
from render_report import inline, markdown_to_html  # noqa: E402


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def test_inline_link_quotes_cannot_create_html_attributes_and_text_is_preserved():
    source = 'See [normal link](https://example.test/path) and [quoted](https://example.test/" autofocus onfocus="alert(1)) with "visible quotes".'

    parser = LinkParser()
    parser.feed(inline(source))

    assert len(parser.links) == 2
    assert parser.links[0][1] == {"href": "https://example.test/path"}
    assert parser.links[1][1] == {
        "href": 'https://example.test/" autofocus onfocus="alert(1',
    }
    visible_text = "".join(parser.text)
    assert "normal link" in visible_text
    assert "quoted" in visible_text
    assert 'with "visible quotes".' in visible_text


def test_main_findings_show_field_table_and_embedded_screenshot_before_appendix(tmp_path: Path):
    import pymupdf
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
    pix.clear_with(255)
    pix.save(evidence / "F-001-001.png")
    source = (
        "# 审核报告\n## 问题清单\n"
        "| 序号/FID | 规则号 | 复核结果 | 最终等级 | 页码 | 位置 | 问题摘要 | 理由/依据 | 规则来源 |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| F-001-001 | R18 | 成立 | C | 第5页 | 备注 | 英文语法错误 | 模型的最终理由 | 内置 |\n"
        "# 附录：分项目审核原文\n历史审核正文。\n"
    )
    rendered = markdown_to_html(source, tmp_path)
    assert 'class="check-point finding-point"' in rendered
    assert 'class="field-table"' in rendered
    assert 'src="data:image/png;base64,' in rendered.split("附录：分项目审核原文")[0]
    assert "模型的最终理由" in rendered


def test_each_rule_has_its_own_table_while_numeric_readings_stay_in_grid(tmp_path: Path):
    rendered = markdown_to_html(
        "| # | 模块 | 检查项 | 等级 | 结果 | 证据位置/说明 |\n|---|---|---|---|---|---|\n"
        "| R01 | 文件 | 页码 | B | 通过 | 共66页 |\n| R02 | 文件 | 签署 | A | 待复核 | 未提交图像 |\n\n"
        "| 页码 | 样品 | 读数 | 平均值 | 单位 | 结论 |\n|---|---|---|---|---|---|\n"
        "| 54 | 02001 | 42.9 | 53.75 | N/50mm | Pass |\n", tmp_path,
    )
    assert rendered.count('class="check-point rule-point"') == 2
    assert rendered.count('class="field-table"') == 2
    assert "42.9" in rendered and "53.75" in rendered


def test_external_document_template_escapes_title_and_footer():
    result = render_report.build_html('<title onload="x">', "<p>safe body</p>", "<footer onload=x>")
    assert "&lt;title onload=&quot;x&quot;&gt;" in result
    assert "&lt;footer onload=x&gt;" in result
    assert "<p>safe body</p>" in result


def test_pending_publication_keeps_model_pass_verdict_neutral_but_complete_pass_stays_green(tmp_path: Path):
    notice = render_report.load_template("incomplete-notice.md").strip()
    pending_html = markdown_to_html(notice + "\n\n# 审核报告\n\n**总评：通过**\n", tmp_path)
    complete_html = markdown_to_html("# 审核报告\n\n**总评：通过**\n", tmp_path)

    assert 'class="verdict verdict-pending"' in pending_html
    assert "模型原始总评：通过" in pending_html
    assert "不表示审核已完整确认" in pending_html
    assert 'class="verdict verdict-pass"' not in pending_html
    assert 'class="verdict verdict-pass"' in complete_html
    assert "模型原始总评" not in complete_html
    assert "不表示审核已完整确认" not in complete_html


def test_template_load_error_names_missing_asset(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(render_report, "TEMPLATE_DIR", tmp_path)
    try:
        render_report.load_template("missing.html")
    except RuntimeError as exc:
        assert "missing.html" in str(exc)
    else:
        raise AssertionError("missing report template should fail clearly")
