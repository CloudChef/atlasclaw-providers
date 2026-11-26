# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "audit-report" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit_project_prompts import build_index_chunk_prompt, build_index_merge_prompt  # noqa: E402


def test_chunk_prompt_is_bounded_and_supplies_previous_scan_as_untrusted_continuation_hint() -> None:
    previous = '{"reviewed_pages":[1,2],"segments":[{"id":"stable-1","title":"项目A"}]}'
    prompt = build_index_chunk_prompt(
        {2: "## Page 2\nprevious page", 3: "## Page 3\nproject row", 4: "## Page 4\ncontinued row"},
        [3, 4], [2], 90, 2, 3,
        previous_scan_raw=previous,
    )

    assert "reviewed_pages` 是可省略的历史兼容元数据" in prompt
    assert "不可信为正式页覆盖证明" in prompt
    assert "## Page 3\nproject row" in prompt and "## Page 4\ncontinued row" in prompt
    assert "## Page 2\nprevious page" in prompt
    assert previous in prompt
    assert "没有提交 PDF 页面图像、照片像素或截图" in prompt
    assert "完整规则JSON" not in prompt and "MATERIAL_BODY" not in prompt
    assert "不属于当前分段的正式审核页" in prompt
    assert "start_evidence" in prompt and "end_evidence" in prompt
    assert "start_quote" in prompt and "不得引用相邻页或其他页" in prompt
    assert "不能仅因接近下一标题就转归新项目" in prompt
    assert "空白/低文字页不自动终止项目" in prompt
    assert "segments` 只包含检测项目及其对应的结果、续表和文字标注的附件" in prompt
    assert "报告声明、签发记录、修订记录等非检测章节逐页列入 `non_project_pages`" in prompt


def test_merge_prompt_contains_only_chunk_scans_and_does_not_reinclude_report_or_materials() -> None:
    scan = {
        "chunk_index": 1,
        "formal_pages": [1, 2],
        "scan": {"reviewed_pages": [1, 2], "segments": [], "non_project_pages": []},
        "raw_response": '{"reviewed_pages":[1,2],"segments":[],"non_project_pages":[]}',
    }
    prompt = build_index_merge_prompt([scan], 64)

    assert "全文实际页数\n64" in prompt
    assert json.dumps(scan["raw_response"], ensure_ascii=False) in prompt
    assert "全局目录JSON" in prompt
    assert "REPORT_TEXT" not in prompt
    assert "MATERIAL_BODY" not in prompt
    assert "start_evidence`/`end_evidence" in prompt
    assert "空白/低文字页不自动成为结束或非项目页" in prompt
