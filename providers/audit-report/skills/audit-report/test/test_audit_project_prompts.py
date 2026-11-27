from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
REFERENCES = SKILL_ROOT / "references"
sys.path.insert(0, str(SCRIPTS))

from audit_project_prompts import (  # noqa: E402
    build_index_prompt,
    build_index_chunk_prompt,
    build_index_merge_prompt,
    build_project_prompt,
    build_summary_prompt,
    build_visual_prompt,
    render_prompt_template,
)
import audit_project_prompts as prompts_module  # noqa: E402


def test_template_loader_substitutes_once_and_reports_placeholder_mismatches(tmp_path, monkeypatch):
    monkeypatch.setattr(prompts_module, "PROMPT_TEMPLATE_DIR", tmp_path)
    (tmp_path / "probe.md").write_text("trusted {{CONTENT}}\n", encoding="utf-8")
    user_text = "{{OTHER}} ${price} $value {brace}"

    assert render_prompt_template("probe.md", CONTENT=user_text) == f"trusted {user_text}"
    with pytest.raises(ValueError, match=r"missing=\['CONTENT'\]"):
        render_prompt_template("probe.md")
    with pytest.raises(ValueError, match=r"unexpected=\['EXTRA'\]"):
        render_prompt_template("probe.md", CONTENT="ok", EXTRA="ignored")


def _rules():
    rules_text = (REFERENCES / "audit-rules.md").read_text(encoding="utf-8")
    pack = json.loads((SKILL_ROOT / "rules" / "builtin" / "rules.json").read_text(encoding="utf-8"))
    return rules_text, pack


def _materials():
    return [
        {"reference_id": "M01", "filename": "ledger.xlsx", "kind": "ledger", "sha256": "ledger-hash",
         "content": "[仪器表!A2] DEV-01\n[仪器表!F2] 2027-01-01"},
        {"reference_id": "M02", "filename": "standard.xlsx", "kind": "standard", "sha256": "standard-hash",
         "content": "[目录!A1] ISO 1234\n[目录!B1] edition-index-only"},
    ]


def test_index_prompt_is_json_only_complete_and_text_only():
    report = "## Page 1\nSYNTHETIC_REPORT_START\n## Page 2\nSYNTHETIC_REPORT_END"
    prompt = build_index_prompt(report, 2)
    rules_text, pack = _rules()
    text_contract = (REFERENCES / "audit-text-evidence.md").read_text(encoding="utf-8")

    assert report in prompt and rules_text in prompt and text_contract in prompt
    assert "只输出一个 JSON 对象" in prompt
    assert '"projects"' in prompt and '"page_start"' in prompt
    assert "当前审核请求仅提交脱敏原生文本" in prompt
    assert "不得声称看过图片" in prompt
    for rule in pack["rules"]:
        assert rule["title"] in prompt


def test_chunk_prompt_keeps_bounded_text_context_and_previous_scan_only():
    previous = '{"reviewed_pages":[1,2],"segments":[{"id":"stable-id","title":"A"}]}'
    prompt = build_index_chunk_prompt(
        {2: "## Page 2\nprevious context", 3: "## Page 3\nproject start", 4: "## Page 4\ncontinued table"},
        [3, 4], [2], 90, 2, 3, previous_scan_raw=previous,
    )
    contract = (REFERENCES / "audit-project-index-chunk.md").read_text(encoding="utf-8")

    assert contract in prompt and previous in prompt
    assert "## Page 3\nproject start" in prompt and "## Page 4\ncontinued table" in prompt
    assert "## Page 2\nprevious context" in prompt
    assert "reviewed_pages` 是可省略的历史兼容元数据" in prompt
    assert "不可信为正式页覆盖证明" in prompt
    assert "正式页分类须由segments和non_project_pages覆盖" in prompt or "共同完整覆盖本段全部正式页" in prompt
    assert "没有提交 PDF 页面图像、照片像素或截图" in prompt
    assert "VISUAL_RAW" not in prompt and "MATERIAL_BODY" not in prompt


def test_index_merge_prompt_uses_validated_scans_only():
    scan = {"chunk_index": 1, "formal_pages": [1, 2], "raw_response": '{"reviewed_pages":[1,2]}'}
    prompt = build_index_merge_prompt([scan], 2)
    assert json.dumps([scan], ensure_ascii=False, indent=2) in prompt
    assert "全文实际页数\n2" in prompt
    assert "REPORT_TEXT" not in prompt and "MATERIAL_BODY" not in prompt
    assert "文本证据边界" in prompt


def test_project_prompt_contains_complete_rules_native_text_all_materials_and_tail_manifest():
    project = {"id": "P-03", "title": "Synthetic project", "page_start": 21, "page_end": 22}
    project_text = "## Page 21\nPROJECT_FIRST_SENTINEL\n## Page 22\nPROJECT_LAST_SENTINEL"
    frontmatter = "## Page 1\nFRONTMATTER_SENTINEL"
    materials = _materials()
    prompt = build_project_prompt(project, project_text, frontmatter, materials, 3)
    rules_text, pack = _rules()
    materials_contract = (REFERENCES / "uploaded-materials-audit.md").read_text(encoding="utf-8")
    text_contract = (REFERENCES / "audit-text-evidence.md").read_text(encoding="utf-8")

    assert project_text in prompt and frontmatter in prompt
    assert rules_text in prompt and materials_contract in prompt and text_contract in prompt
    assert "PROJECT_FIRST_SENTINEL" in prompt and "PROJECT_LAST_SENTINEL" in prompt
    for material in materials:
        assert material["filename"] in prompt and material["content"] in prompt
        assert material["sha256"] in prompt and material["reference_id"] in prompt
    assert "[仪器表!A2] DEV-01" in prompt and "[目录!B1] edition-index-only" in prompt
    assert prompt.rindex("</MATERIAL_BODY>") < prompt.index("<FRONTMATTER>")
    assert prompt.index("<FRONTMATTER>") < prompt.index("<PROJECT_SOURCE>")
    assert prompt.index("<PROJECT_SOURCE>") < prompt.index("# 文本证据边界")
    assert prompt.index("# 文本证据边界") < prompt.index("# 本次任务：一个项目的完整审核")
    assert prompt.index("# 上传资料逐项目核查补充合同") < prompt.index("<CURRENT_MATERIAL_MANIFEST>")
    assert "rules_dir" not in prompt
    assert "只输出本项目完整 Markdown" in prompt
    assert "对容差 `a±b`，先依据该原文明确计算下限 `a-b` 与上限 `a+b`" in prompt
    assert "定性结果不得借用相邻的数值字段补成读数" in prompt
    assert "完整、合法的数字不能仅因偏离很大或与邻行不相近，就假定漏写小数点" in prompt
    assert "≤ 50 字" not in prompt and "≤50字" not in prompt
    assert "不设引用长度或发现数量上限" in prompt
    assert "校准起始/生效日期或历史证书" in prompt
    assert "引文确实位于所列 PDF 实际页码" in prompt
    assert "区分环境应力、存储或老化条件与试验前、中、后的功能/电参数测量条件" in prompt
    assert "只有同一阶段、同一对象的原文证据能支持偏离判断" in prompt
    assert "无需在详情重复" in prompt
    assert "规则 JSON 的 `severity` 原值" in prompt
    assert "视觉核查原始结果" not in prompt
    assert "小页组数值核查原始记录" not in prompt
    assert "待复核候选" not in prompt and "INITIAL_DRAFT" not in prompt
    assert [rule["id"] for rule in pack["rules"]] == [f"R{i:02d}" for i in range(1, 47)]
    assert all(f'"id": "{rule["id"]}"' in prompt for rule in pack["rules"])


def test_summary_prompt_keeps_all_source_materials_reviews_and_reference_index():
    report = "## Page 1\nREPORT_FULL_TEXT_SENTINEL"
    materials = _materials()
    reviews = [
        {"project_id": "P1", "project_index": 1, "markdown": "## 项目 P1\n### F-001001 [A] one"},
        {"project_id": "P2", "project_index": 1000, "markdown": "## 项目 P2\n#### F-1000-1001 [B] two"},
    ]
    prompt = build_summary_prompt(report, materials, 1, reviews)
    rules_text, pack = _rules()
    materials_contract = (REFERENCES / "uploaded-materials-audit.md").read_text(encoding="utf-8")
    text_contract = (REFERENCES / "audit-text-evidence.md").read_text(encoding="utf-8")

    assert report in prompt and rules_text in prompt and materials_contract in prompt and text_contract in prompt
    for item in materials:
        assert item["content"] in prompt and item["filename"] in prompt
    for item in reviews:
        assert item["markdown"] in prompt and item["project_id"] in prompt
    assert "F-001001" in prompt and "F-1000-1001" in prompt
    assert '<ACCEPTED_PROJECT_FINDING_INDEX>' in prompt
    assert "不得因标题层级或位置遗漏" in prompt
    assert "复核结果" in prompt and "最终等级" in prompt
    assert "此索引不代表问题已成立" in prompt
    assert "成立、待复核或撤回及依据" in prompt
    assert "附录不改写，作为历史审核记录保留" in prompt
    assert "最终结论以主报告处置为准" in prompt
    assert prompt.index(report) < prompt.index(materials[0]["content"])
    assert prompt.index(materials[-1]["content"]) < prompt.index(reviews[0]["markdown"])
    assert prompt.index(reviews[-1]["markdown"]) < prompt.index("# 文本证据边界")
    assert prompt.index("# 文本证据边界") < prompt.index("# 本次任务：全局审核与汇总")
    assert prompt.index("# 上传资料逐项目核查补充合同") < prompt.index("<CURRENT_MATERIAL_MANIFEST>")
    assert prompt.index("<CURRENT_MATERIAL_MANIFEST>") < prompt.index("<ACCEPTED_PROJECT_FINDING_INDEX>")
    assert prompt.index("<ACCEPTED_PROJECT_FINDING_INDEX>") < prompt.index("# 输出格式")
    assert "视觉核查原始结果" not in prompt and "NUMERIC_REVIEW_RAW" not in prompt
    assert {f"R{i:02d}" for i in range(1, 20)} <= {rule["id"] for rule in pack["rules"]}


def test_summary_runtime_timestamp_uses_local_timezone_and_preserves_source_dates(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 26, 9, 8, 7, tzinfo=timezone(timedelta(hours=8)))

        def astimezone(self, tz=None):
            return self

    monkeypatch.setattr(prompts_module, "datetime", FixedDateTime)
    report = "## Page 1\n检测日期：2026-11-20；签发日期：2026-11-22。"
    materials = [{"filename": "ledger.xlsx", "kind": "ledger", "content": "版本日期：2026-10-14"}]
    prompt = build_summary_prompt(report, materials, 1, [])

    assert "运行环境当前本地时间（含时区）：2026-11-26T09:08:07+08:00" in prompt
    assert "不得替代、推断或改写源报告的检测/签发日期及上传资料版本日期" in prompt
    assert report in prompt and "版本日期：2026-10-14" in prompt


def test_prompts_use_explicit_rules_snapshot_directory(tmp_path):
    rules_dir = tmp_path / "rules-snapshot"
    shutil.copytree(SKILL_ROOT / "rules", rules_dir)
    builtin = rules_dir / "builtin" / "rules.json"
    payload = json.loads(builtin.read_text(encoding="utf-8"))
    payload["rules"][0]["title"] = "snapshot-specific R01 title"
    builtin.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    project = build_project_prompt({"id": "P", "title": "T", "page_start": 1, "page_end": 1}, "text", "front", [], 1, rules_dir=rules_dir)
    summary = build_summary_prompt("report", [], 1, [], rules_dir=rules_dir)
    assert "snapshot-specific R01 title" in project and "snapshot-specific R01 title" in summary


def test_rules_config_can_point_to_absolute_builtin_pack_path(tmp_path):
    rules_dir = tmp_path / "rules-snapshot"
    builtin = rules_dir / "custom" / "builtin.json"
    builtin.parent.mkdir(parents=True)
    shutil.copy2(SKILL_ROOT / "rules" / "builtin" / "rules.json", builtin)
    (rules_dir / "config.json").write_text(
        json.dumps({"version": 1, "builtin": str(builtin), "packs": [], "allow_overrides": False}),
        encoding="utf-8",
    )
    prompt = build_project_prompt({"id": "P", "title": "T", "page_start": 1, "page_end": 1}, "text", "front", [], 1, rules_dir=rules_dir)
    assert "R46" in prompt and "完整内置 JSON 规则源" not in prompt


def test_default_rules_root_honours_audit_rules_dir_environment(tmp_path, monkeypatch):
    rules_dir = tmp_path / "environment-rules"
    shutil.copytree(SKILL_ROOT / "rules", rules_dir)
    builtin = rules_dir / "builtin" / "rules.json"
    payload = json.loads(builtin.read_text(encoding="utf-8"))
    payload["rules"][0]["title"] = "environment-root R01 title"
    builtin.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setenv("AUDIT_RULES_DIR", str(rules_dir))
    prompt = build_project_prompt({"id": "P", "title": "T", "page_start": 1, "page_end": 1}, "text", "front", [], 1)
    assert "environment-root R01 title" in prompt


def test_visual_prompt_includes_visual_rules_and_page_contract():
    prompt = build_visual_prompt(
        "## Page 1\n\nSynthetic text", [1], [], page_count=1,
    )
    assert "R14" in prompt and "R30" in prompt and "R34" in prompt
    assert "audit-visual-review" in prompt or "页面组视觉核查合同" in prompt
    assert "### Page N" in prompt
    assert "R01" not in prompt  # non-visual page-number rule is not sent
