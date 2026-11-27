# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import pytest
import pymupdf

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "audit-report" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_workflow  # noqa: E402
from run_document_audit import validate_markdown  # noqa: E402


def _project(project_id: str, issue_id: str, filenames: tuple[str, ...]) -> str:
    ledger_section = "\n".join(
        f"- M{index:02d} {name}：已逐项核查。" for index, name in enumerate(filenames, 1)
    ) or "无设备台账资料或设备记录。"
    return (
        f"## 项目 {project_id} 项目核查\n"
        "### 核查依据\n报告第2页。\n"
        "### 数值核查\n完整列出本项目数值。\n"
        "### 设备台账\n" + ledger_section + "\n### 项目问题\n"
        + f"### {issue_id} [A] 核查说明（R10）\n- **规则号**：`R10`\n- **等级**：`A · 严重`\n问题详情。\n"
    )


def _summary() -> str:
    from _rules import load_rules

    rows = [
        "# 审核报告", "**总评：通过**", "## 检查覆盖表",
        "| # | 模块 | 检查项 | 等级 | 结果 | 证据位置/说明 |", "| --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(f"| {rule} | 模块 | 检查项 | B | 通过 | 证据 |" for rule in load_rules().ids)
    rows.extend([
        "## 复核结果", "| FID | 复核结果 | 最终等级 | 理由/依据 |", "| --- | --- | --- | --- |",
        "| F-000001 | 成立 | B | 已核实 |", "## 全局问题", "### F-000001 [B] 全局问题（R01）",
                 "- **规则号**：`R01`", "- **等级**：`B · 主要`", "详情。"])
    return "\n".join(rows)


def _install_builders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        audit_workflow,
        "_load_builders",
        lambda: (
            lambda report, count: f"INDEX {count}\n{report}",
            lambda project, text, frontmatter, materials, index, **kwargs: (
                f"PROJECT {index} {project['id']}\n{text}\nFRONT\n{frontmatter}\n"
                + "\n".join(item["reference_id"] + " " + item["filename"] + "\n" + item["content"] for item in materials)
            ),
            lambda report, materials, count, reviews, **kwargs: (
                f"SUMMARY {count}\n{report}\n"
                + "\n".join(item["reference_id"] + " " + item["filename"] + "\n" + item["content"] for item in materials)
                + "\n".join(review["markdown"] for review in reviews)
            ),
        ),
    )


@pytest.mark.parametrize("reference", ["M01", "M01中的设备记录", "设备台账.xlsx"])
def test_project_can_identify_each_material_once(reference: str) -> None:
    body = _project("6.1", "F-001-001", ()).replace("无设备台账资料或设备记录。", reference)
    assert audit_workflow._check_project(
        body, 1, [{"reference_id": "M01", "filename": "设备台账.xlsx"}]
    ) == ["F-001-001"]


@pytest.mark.parametrize("reference", ["未提供资料", "M010", "prefixM01"])
def test_project_still_rejects_an_unidentified_material(reference: str) -> None:
    body = _project("6.1", "F-001-001", ()).replace("无设备台账资料或设备记录。", reference)
    with pytest.raises(ValueError, match="identify material M01"):
        audit_workflow._check_project(body, 1, [{"reference_id": "M01", "filename": "设备台账.xlsx"}])


class _CodedSubmitError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _request_fixture() -> tuple[str, str, str]:
    files = ("设备台账.xlsx",)
    index = json.dumps({
        "projects": [{"id": "6.1", "title": "存储", "page_start": 1, "page_end": 1}],
        "no_projects_reason": "",
    }, ensure_ascii=False)
    project = _project("6.1", "F-001001", files)
    return index, project, _summary()


@pytest.mark.asyncio
async def test_all_projects_run_without_local_concurrency_cap_and_keep_full_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_builders(monkeypatch)
    files = ("设备台账.xlsx", "检测标准.xlsx")
    index = json.dumps({
        "projects": [
            {"id": "6.1", "title": "存储", "page_start": 2, "page_end": 3},
            {"id": "6.2", "title": "温度", "page_start": 4, "page_end": 4},
            {"id": "6.3", "title": "电压", "page_start": 5, "page_end": 5},
        ],
        "no_projects_reason": "",
    }, ensure_ascii=False)
    project_responses = {
        "6.1": _project("6.1", "F-001001", files),
        "6.2": _project("6.2", "F-002001", files),
        "6.3": _project("6.3", "F-003001", files),
    }
    active = 0
    peak = 0
    prompts: list[str] = []

    async def submit(prompt: str) -> str:
        nonlocal active, peak
        prompts.append(prompt)
        if prompt.startswith("INDEX"):
            return index
        if prompt.startswith("PROJECT"):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            project_id = next(project_id for project_id in project_responses if f"PROJECT " in prompt and project_id in prompt)
            active -= 1
            return project_responses[project_id]
        assert prompt.startswith("SUMMARY")
        return _summary()

    long_material = "sheet row evidence " + ("完整原始单元格内容。" * 10000) + " MATERIAL-END-SENTINEL"
    materials = [
        {"filename": files[0], "kind": "ledger", "content": long_material, "sha256": "a" * 64},
        {"filename": files[1], "kind": "standard", "content": "standard evidence", "sha256": "b" * 64},
    ]
    report = "## Page 1\nFront page\n## Page 2\nPage two full\n## Page 3\nPage three full\n## Page 4\nPage four full\n## Page 5\nPage five full"
    events: list[dict] = []

    result = await audit_workflow.execute_audit(
        report, materials, 5, submit, tmp_path, on_progress=lambda event: _record(events, event)
    )

    assert peak == 3
    assert result.startswith("> 报告未完成：模型未提供部分候选处置结论")
    assert all(f"| F-00{index}001 | 待复核 | — |" in result for index in (1, 2, 3))
    assert "# 附录：分项目审核原文" in result
    assert "Page two full" in prompts[1] and "Page three full" in prompts[1]
    assert "Page four full" in prompts[2]
    assert "Page five full" in prompts[3]
    assert "Front page" in prompts[1] and "Front page" in prompts[2]
    for filename in files:
        assert all(filename in prompt for prompt in prompts[1:])
    assert all("MATERIAL-END-SENTINEL" in prompt for prompt in prompts[1:])
    assert (tmp_path / "index-raw.txt").read_text(encoding="utf-8") == index
    assert (tmp_path / "projects" / "001-raw.md").read_text(encoding="utf-8") == project_responses["6.1"]
    assert (tmp_path / "projects" / "002-raw.md").read_text(encoding="utf-8") == project_responses["6.2"]
    assert (tmp_path / "projects" / "003-raw.md").read_text(encoding="utf-8") == project_responses["6.3"]
    assert (tmp_path / "audit-main-raw.md").read_text(encoding="utf-8") == _summary()
    assert (tmp_path / "audit.md").read_text(encoding="utf-8") == result
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    assert manifest["materials"][0]["sha256"] == "a" * 64
    assert [item["status"] for item in manifest["projects"]] == ["complete", "complete", "complete"]
    assert [item["stage"].split(":", 1)[0] for item in manifest["requests"]] == [
        "index", "project-review", "project-review", "project-review", "summary",
    ]
    assert all("images" not in item and "visual" not in item["stage"] for item in manifest["requests"])
    assert manifest["requests"][0]["source_materials"] == []
    assert manifest["requests"][0]["prompt_sha256"] == hashlib.sha256(prompts[0].encode("utf-8")).hexdigest()
    assert manifest["requests"][0]["prompt_characters"] == len(prompts[0])
    assert manifest["requests"][1]["source_pages"] == [1, 2, 3]
    assert manifest["requests"][1]["source_materials"] == ["M01", "M02"]
    assert any(event["stage"] == "projects" and event["completed"] == 3 for event in events)


@pytest.mark.asyncio
async def test_long_index_scans_all_pages_in_order_and_merges_cross_chunk_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_builders(monkeypatch)
    chunk_prompts: list[dict] = []
    merge_prompts: list[dict] = []

    def build_chunk(page_text, formal_pages, context_pages, page_count, chunk_index, chunk_count,
                    *, previous_scan_raw=None):
        prompt = {
            "kind": "chunk", "formal_pages": formal_pages, "context_pages": context_pages,
            "page_text": page_text, "previous_scan_raw": previous_scan_raw,
        }
        chunk_prompts.append(prompt)
        return json.dumps(prompt, ensure_ascii=False)

    def build_merge(scans, page_count):
        payload = {"kind": "merge", "page_count": page_count, "scans": scans}
        merge_prompts.append(payload)
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(audit_workflow, "_load_chunk_index_builders", lambda: (build_chunk, build_merge))
    raw_chunks: dict[int, str] = {}
    submit_order: list[str] = []

    async def submit(prompt: str) -> str:
        if prompt.startswith("PROJECT"):
            return _project("6.1", "F-001001", ())
        if prompt.startswith("SUMMARY"):
            return _summary()
        request = json.loads(prompt.splitlines()[0])
        submit_order.append(request["kind"] + (f":{len(submit_order) + 1}"))
        if request["kind"] == "merge":
            ids = {segment["id"] for scan in request["scans"] for segment in scan["scan"]["segments"]}
            assert ids == {"6.1"}
            return json.dumps({"projects": [{"id": "6.1", "title": "温度项目", "page_start": 10,
                                               "page_end": 65}], "no_projects_reason": ""}, ensure_ascii=False)

        chunk_number = len(raw_chunks) + 1
        pages = request["formal_pages"]
        if chunk_number == 1:
            body = {
                "reviewed_pages": pages,
                "segments": [{"id": "6.1", "title": "温度项目", "page_start": 10, "page_end": 32,
                              "start_status": "starts_here", "end_status": "continues_into_next",
                              "start_quote": "source page 10"}],
                "non_project_pages": [{"page": p, "reason": "前置全局内容"} for p in range(1, 10)],
            }
        elif chunk_number == 2:
            body = {
                "reviewed_pages": pages,
                "segments": [{"id": "6.1", "title": "温度项目", "page_start": 33, "page_end": 64,
                              "start_status": "continues_from_previous", "end_status": "continues_into_next"}],
                "non_project_pages": [],
            }
        elif chunk_number == 3:
            body = {
                "reviewed_pages": pages,
                "segments": [{"id": "6.1", "title": "温度项目", "page_start": 65, "page_end": 65,
                              "start_status": "continues_from_previous", "end_status": "ends_here"}],
                "non_project_pages": [{"page": p, "reason": "项目外全局内容"} for p in range(66, 71)],
            }
        else:
            raise AssertionError("unexpected extra chunk request")
        raw = json.dumps(body, ensure_ascii=False)
        raw_chunks[chunk_number] = raw
        return raw

    report = "\n\n".join(f"## Page {page}\nsource page {page}" for page in range(1, 71))
    result = await audit_workflow.execute_audit(report, [], 70, submit, tmp_path)

    assert result.startswith("> 报告未完成：模型未提供部分候选处置结论")
    assert "| F-001001 | 待复核 | — |" in result
    assert "### F-001001 [A]" in result
    assert [prompt["formal_pages"] for prompt in chunk_prompts] == [list(range(1, 33)), list(range(33, 65)), list(range(65, 71))]
    assert chunk_prompts[0]["context_pages"] == [33]
    assert chunk_prompts[1]["context_pages"] == [32, 65]
    assert chunk_prompts[2]["context_pages"] == [64]
    assert chunk_prompts[1]["previous_scan_raw"] == raw_chunks[1]
    assert chunk_prompts[2]["previous_scan_raw"] == raw_chunks[2]
    assert [entry.split(":", 1)[0] for entry in submit_order] == ["chunk", "chunk", "chunk", "merge"]
    assert "source page 32" in chunk_prompts[1]["page_text"][32]
    assert "source page 33" in chunk_prompts[1]["page_text"][33]
    assert "source page 65" in chunk_prompts[1]["page_text"][65]
    assert "source page 70" in chunk_prompts[2]["page_text"][70]
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    assert [chunk["status"] for chunk in manifest["index"]["chunks"]] == ["complete"] * 3
    assert [chunk["formal_pages"][0] for chunk in manifest["index"]["chunks"]] == [1, 33, 65]
    assert all((tmp_path / chunk["completed_response_file"]).is_file()
               for chunk in manifest["index"]["chunks"])
    assert manifest["index"]["chunk_project_ids"] == ["6.1"]


@pytest.mark.asyncio
async def test_long_index_stops_on_unclassified_chunk_and_never_merges_or_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_builders(monkeypatch)
    chunk_number = 0

    def build_chunk(page_text, formal_pages, context_pages, page_count, chunk_index, chunk_count,
                    *, previous_scan_raw=None):
        return json.dumps({"formal_pages": formal_pages, "chunk_index": chunk_index})

    def build_merge(scans, page_count):
        return "MERGE SHOULD NEVER RUN"

    monkeypatch.setattr(audit_workflow, "_load_chunk_index_builders", lambda: (build_chunk, build_merge))

    async def submit(prompt: str) -> str:
        nonlocal chunk_number
        request = json.loads(prompt.splitlines()[0])
        chunk_number = request["chunk_index"]
        if chunk_number == 1:
            return json.dumps({"reviewed_pages": request["formal_pages"], "segments": [],
                               "non_project_pages": [{"page": page, "reason": "无项目内容"}
                                                     for page in request["formal_pages"]]})
        # The hint is ignored; canonical classifications still leave the second chunk uncovered.
        return json.dumps({"reviewed_pages": [], "segments": [], "non_project_pages": []})

    report = "\n\n".join(f"## Page {page}\nsource page {page}" for page in range(1, 71))
    with pytest.raises(ValueError, match="leaves formal pages unclassified"):
        await audit_workflow.execute_audit(report, [], 70, submit, tmp_path)

    assert chunk_number == 2
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    assert [chunk["status"] for chunk in manifest["index"]["chunks"]] == ["complete", "failed"]
    assert len(manifest["index"]["chunks"][1]["attempts"]) == 2
    assert len(manifest["index"]["chunks"]) == 2
    assert not list(tmp_path.glob("index-merge-raw.txt"))
    assert not (tmp_path / "index.json").exists()
    assert not (tmp_path / "audit-main-raw.md").exists()


@pytest.mark.asyncio
async def test_long_index_accepts_flagless_project_continuation_across_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_builders(monkeypatch)

    def build_chunk(page_text, formal_pages, context_pages, page_count, chunk_index, chunk_count,
                    *, previous_scan_raw=None):
        return json.dumps({"formal_pages": formal_pages, "chunk_index": chunk_index})

    def build_merge(scans, page_count):
        return json.dumps({"projects": [{"id": "P", "title": "Project", "page_start": 1,
                                          "page_end": 40}], "no_projects_reason": ""})

    monkeypatch.setattr(audit_workflow, "_load_chunk_index_builders", lambda: (build_chunk, build_merge))

    calls = 0

    async def submit(prompt: str) -> str:
        nonlocal calls
        calls += 1
        if calls <= 2:
            pages = list(range(1, 33)) if calls == 1 else list(range(33, 41))
        else:
            if calls == 3:
                return build_merge([], 40)
            if calls == 4:
                return _project("P", "F-001001", ())
            return _summary()
        if calls == 1:
            segment = {"id": "P", "title": "Project", "page_start": pages[0],
                       "page_end": pages[-1], "start_quote": "page 1"}
            return json.dumps({"segments": [segment]})
        segment = {"id": "P", "title": "Project", "page_start": pages[0], "page_end": pages[-1]}
        return json.dumps({"segments": [segment]})

    report = "\n\n".join(f"## Page {page}\npage {page}" for page in range(1, 41))
    await audit_workflow.execute_audit(report, [], 40, submit, tmp_path)
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    assert [chunk["status"] for chunk in manifest["index"]["chunks"]] == ["complete", "complete"]
    assert manifest["index"]["chunk_project_ids"] == ["P"]
    assert (tmp_path / "index.json").is_file()


def test_index_chunk_optional_review_flags_and_empty_containers_still_require_exact_coverage() -> None:
    pages = [1, 2]
    page_map = {1: "## Page 1\nActual project heading", 2: "## Page 2\nProject continuation"}
    valid = {
        "reviewed_pages": [2, 1],
        "segments": [{"id": "P-01", "title": "Project", "page_start": 1, "page_end": 2,
                      "start_quote": "Actual project heading"}],
    }
    scan = audit_workflow._validate_index_chunk(json.dumps(valid), pages, 2, page_map)
    assert scan["project_ids"] == ["P-01"]
    assert "reviewed_pages" not in scan
    assert scan["non_project_pages"] == []

    incomplete = {"segments": [{"id": "P-01", "title": "Project", "page_start": 1, "page_end": 1,
                                 "start_quote": "Actual project heading"}]}
    with pytest.raises(ValueError, match="leaves formal pages unclassified"):
        audit_workflow._validate_index_chunk(json.dumps(incomplete), pages, 2, page_map)

    missing_anchor = {"segments": [{"id": "P-01", "title": "Project", "page_start": 1, "page_end": 2}]}
    with pytest.raises(ValueError, match="new ID without a literal start_quote"):
        audit_workflow._validate_index_chunk(json.dumps(missing_anchor), pages, 2, page_map)


@pytest.mark.asyncio
async def test_long_index_rejects_same_id_segment_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_builders(monkeypatch)

    def build_chunk(page_text, formal_pages, context_pages, page_count, chunk_index, chunk_count,
                    *, previous_scan_raw=None):
        return json.dumps({"chunk_index": chunk_index})

    def build_merge(scans, page_count):
        raise AssertionError("merge must not run when a project has an internal page gap")

    monkeypatch.setattr(audit_workflow, "_load_chunk_index_builders", lambda: (build_chunk, build_merge))

    calls = 0

    async def submit(prompt: str) -> str:
        nonlocal calls
        calls += 1
        if calls <= 2:
            pages = list(range(1, 33)) if calls == 1 else list(range(33, 41))
        else:
            raise AssertionError("merge must not run when a project has an internal page gap")
        if calls == 1:
            segments = [
                {"id": "P", "title": "Project", "page_start": 1, "page_end": 10, "start_quote": "page 1"},
                {"id": "P", "title": "Project", "page_start": 12, "page_end": 32},
            ]
            return json.dumps({"segments": segments, "non_project_pages": [{"page": 11, "reason": "中间非项目页"}]})
        return json.dumps({"segments": [{"id": "P", "title": "Project", "page_start": 33, "page_end": 40}]})

    report = "\n\n".join(f"## Page {page}\npage {page}" for page in range(1, 41))
    with pytest.raises(ValueError, match="project P have a gap"):
        await audit_workflow.execute_audit(report, [], 40, submit, tmp_path)
    assert not (tmp_path / "index.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("merge_result, error", [
    ({"projects": [], "no_projects_reason": "none"}, "IDs differ from chunk scans"),
    ({"projects": [{"id": "P", "title": "Project", "page_start": 1, "page_end": 39}],
      "no_projects_reason": ""}, "range for project P must match"),
])
async def test_long_index_rejects_merge_that_drops_id_or_changes_exact_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, merge_result: dict, error: str,
) -> None:
    _install_builders(monkeypatch)

    def build_chunk(page_text, formal_pages, context_pages, page_count, chunk_index, chunk_count,
                    *, previous_scan_raw=None):
        return json.dumps({"chunk_index": chunk_index})

    def build_merge(scans, page_count):
        return json.dumps(merge_result)

    monkeypatch.setattr(audit_workflow, "_load_chunk_index_builders", lambda: (build_chunk, build_merge))
    calls = 0

    async def submit(prompt: str) -> str:
        nonlocal calls
        calls += 1
        if calls >= 3:
            return json.dumps(merge_result)
        pages = list(range(1, 33)) if calls == 1 else list(range(33, 41))
        segment = {"id": "P", "title": "Project", "page_start": pages[0], "page_end": pages[-1]}
        if calls == 1:
            segment["start_quote"] = "page 1"
        return json.dumps({"segments": [segment]})

    report = "\n\n".join(f"## Page {page}\npage {page}" for page in range(1, 41))
    with pytest.raises(ValueError, match=error):
        await audit_workflow.execute_audit(report, [], 40, submit, tmp_path)
    assert not (tmp_path / "index.json").exists()


def test_project_heading_accepts_tight_and_spaced_numeric_titles() -> None:
    from audit_workflow import _check_project

    for heading in ("## 项目6.1", "##项目6.1", "## 项目 6.1"):
        markdown = _project("6.1", "F-001001", ()).replace("## 项目 6.1 项目核查", heading)
        assert _check_project(markdown, 1, []) == ["F-001001"]


def test_index_requires_reason_only_when_project_array_is_empty() -> None:
    partial_with_reason = {
        "projects": [{"id": "6.28", "title": "项目", "page_start": 456, "page_end": 472}],
        "no_projects_reason": "只看到部分页面，其他页面未识别",
    }
    assert audit_workflow._parse_index(json.dumps(partial_with_reason, ensure_ascii=False), 472)["projects"]

    complete_nonempty = {
        "projects": [{"id": "6.28", "title": "项目", "page_start": 456, "page_end": 472}],
        "no_projects_reason": "",
    }
    assert audit_workflow._parse_index(json.dumps(complete_nonempty), 472)["projects"]

    omitted_reason = {"projects": [{"id": "6.1", "title": "项目", "page_start": 1, "page_end": 2}]}
    assert "no_projects_reason" not in audit_workflow._parse_index(json.dumps(omitted_reason), 472)

    no_projects = {"projects": [], "no_projects_reason": "报告没有可识别的独立项目"}
    assert audit_workflow._parse_index(json.dumps(no_projects, ensure_ascii=False), 472) == no_projects


def test_index_chunk_start_quote_must_be_on_declared_native_page() -> None:
    pages = [1, 2]
    page_map = {1: "## Page 1\npreceding appendix", 2: "## Page 2\nActual project heading"}
    misplaced = {
        "reviewed_pages": pages,
        "segments": [{"id": "P-01", "title": "Project", "page_start": 1, "page_end": 2,
                      "start_status": "starts_here", "end_status": "ends_here",
                      "start_quote": "Actual project heading"}],
        "non_project_pages": [],
    }
    with pytest.raises(ValueError, match="start_quote.*start page 1"):
        audit_workflow._validate_index_chunk(json.dumps(misplaced), pages, 2, page_map)

    corrected = json.loads(json.dumps(misplaced))
    corrected["segments"][0]["page_start"] = 2
    corrected["segments"][0]["page_end"] = 2
    corrected["non_project_pages"] = [{"page": 1, "reason": "前置附录页"}]
    validated = audit_workflow._validate_index_chunk(json.dumps(corrected), pages, 2, page_map)
    assert validated["project_ids"] == ["P-01"]


def test_index_chunk_start_quote_ignores_whitespace_only_but_not_text_or_page_changes() -> None:
    pages = [12, 13]
    source = "7.4\n检测项目Test Item: D-02 耐腐蚀试验Corrosion test"
    page_map = {12: f"## Page 12\n{source}", 13: "## Page 13\nAdjacent page title"}
    scan = {
        "reviewed_pages": pages,
        "segments": [{
            "id": "P-04", "title": "Corrosion test", "page_start": 12, "page_end": 12,
            "start_status": "starts_here", "end_status": "ends_here",
            "start_quote": "7.4 检测项目Test Item: D-02 耐腐蚀试验 Corrosion test",
        }],
        "non_project_pages": [{"page": 13, "reason": "后续非项目页"}],
    }
    assert audit_workflow._validate_index_chunk(json.dumps(scan, ensure_ascii=False), pages, 13, page_map)["project_ids"] == ["P-04"]

    altered = json.loads(json.dumps(scan, ensure_ascii=False))
    altered["segments"][0]["start_quote"] = altered["segments"][0]["start_quote"].replace("D-02", "D-03")
    with pytest.raises(ValueError, match="start_quote.*start page 12"):
        audit_workflow._validate_index_chunk(json.dumps(altered, ensure_ascii=False), pages, 13, page_map)

    neighbor = json.loads(json.dumps(scan, ensure_ascii=False))
    neighbor["segments"][0]["start_quote"] = "Adjacent page title"
    with pytest.raises(ValueError, match="start_quote.*start page 12"):
        audit_workflow._validate_index_chunk(json.dumps(neighbor, ensure_ascii=False), pages, 13, page_map)


@pytest.mark.asyncio
async def test_long_index_retries_and_preserves_chunk_raw_when_start_quote_is_on_wrong_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_builders(monkeypatch)
    attempts = {1: 0, 2: 0}

    def build_chunk(page_text, formal_pages, context_pages, page_count, chunk_index, chunk_count,
                    *, previous_scan_raw=None):
        return json.dumps({"chunk_index": chunk_index, "formal_pages": formal_pages,
                           "page_text": page_text, "previous_scan_raw": previous_scan_raw})

    def build_merge(scans, page_count):
        return json.dumps({"scans": scans})

    monkeypatch.setattr(audit_workflow, "_load_chunk_index_builders", lambda: (build_chunk, build_merge))
    original_bad = None
    prompts: list[str] = []

    async def submit(prompt: str) -> str:
        nonlocal original_bad
        prompts.append(prompt)
        if prompt.startswith("PROJECT"):
            return _project("P-01", "F-001001", ())
        if prompt.startswith("SUMMARY"):
            return _summary()
        request = json.loads(prompt.splitlines()[0])
        if "scans" in request:
            return json.dumps({"projects": [{"id": "P-01", "title": "Project", "page_start": 2,
                                               "page_end": 33}], "no_projects_reason": ""})
        chunk_index = request["chunk_index"]
        attempts[chunk_index] += 1
        pages = request["formal_pages"]
        if chunk_index == 1:
            if attempts[1] == 1:
                body = {"reviewed_pages": pages,
                        "segments": [{"id": "P-01", "title": "Project", "page_start": 1, "page_end": 32,
                                      "start_status": "starts_here", "end_status": "continues_into_next",
                                      "start_quote": "Actual project heading"}],
                        "non_project_pages": []}
                original_bad = json.dumps(body)
                return original_bad
            body = {"reviewed_pages": pages,
                    "segments": [{"id": "P-01", "title": "Project", "page_start": 2, "page_end": 32,
                                  "start_status": "starts_here", "end_status": "continues_into_next",
                                  "start_quote": "Actual project heading"}],
                    "non_project_pages": [{"page": 1, "reason": "前置内容"}]}
        else:
            body = {"reviewed_pages": pages,
                    "segments": [{"id": "P-01", "title": "Project", "page_start": 33, "page_end": 33,
                                  "start_status": "continues_from_previous", "end_status": "ends_here"}],
                    "non_project_pages": []}
        return json.dumps(body)

    report = "\n\n".join(
        f"## Page {page}\n{'Actual project heading' if page == 2 else f'page {page} body'}"
        for page in range(1, 34)
    )
    await audit_workflow.execute_audit(report, [], 33, submit, tmp_path)

    first_path = tmp_path / "index-chunks/001-raw.json.txt"
    retry_path = tmp_path / "index-chunks/001-retry-raw.json.txt"
    assert first_path.read_text(encoding="utf-8") == original_bad
    assert retry_path.is_file()
    assert original_bad in prompts[1]
    assert "start_quote is not present on its declared start page 1" in prompts[1]
    assert "重新核对受影响正式页的原生文本" in prompts[1]
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    attempts_record = manifest["index"]["chunks"][0]["attempts"]
    assert len(attempts_record) == 2
    retry_request = next(item for item in manifest["requests"] if item["stage"] == "index-chunk:001"
                         and item["response_file"].endswith("001-retry-raw.json.txt"))
    assert retry_request["prompt_characters"] > 0


def test_project_rejects_empty_fixed_sections_even_if_material_names_are_present() -> None:
    from audit_workflow import _check_project

    markdown = (
        "## 项目 6.1 温度\n"
        "### 核查依据\n"
        "### 数值核查\n"
        "### 设备台账\n"
        "### 项目问题\n"
        "M01 设备台账.xlsx\n"
    )
    with pytest.raises(ValueError, match="empty content.*核查依据"):
        _check_project(markdown, 1, [{"reference_id": "M01", "filename": "设备台账.xlsx"}])


def test_project_issue_block_is_content_of_project_issues_section() -> None:
    from audit_workflow import _check_project

    markdown = (
        "## 项目 6.1 温度\n"
        "### 核查依据\n项目适用规则及来源。\n"
        "### 数值核查\n全部样品值与限值已逐项核对。\n"
        "### 设备台账\n本项目设备及来源行逐台对照。\n"
        "### 项目问题\n"
        "### F-001001 [B] 样品异常（R10）\n"
        "页码与原文证据、边界和影响说明。\n"
    )
    assert _check_project(markdown, 1, []) == ["F-001001"]


@pytest.mark.parametrize("level", ["#", "##", "####", "#####", "######"])
def test_project_rejects_finding_definition_at_wrong_heading_level(level: str) -> None:
    markdown = _project("6.1", "F-001001", ()).replace(
        "### F-001001", f"{level} F-001001", 1
    )
    with pytest.raises(ValueError, match=r"exactly three #.*###"):
        _check = audit_workflow._check_project
        _check(markdown, 1, [])


def test_project_finding_reference_in_prose_or_code_is_not_a_heading_definition() -> None:
    markdown = _project("6.1", "F-001001", ()).replace(
        "### F-001001", "正文引用 F-001001。\n```markdown\n#### F-009999\n```\n### F-001001", 1
    )
    assert audit_workflow._check_project(markdown, 1, []) == ["F-001001"]


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_markdown_normalizes_finding_heading_and_same_line_metadata_without_changing_values(level: int) -> None:
    raw = _project("6.1", "F-001001", ()).replace(
        "### F-001001 [A] 核查说明（R10）",
        f"{'#' * level} F-001001 [A] 实测问题（R10）",
    ).replace(
        "问题详情。",
        "- **规则号**：`R10`；**等级**：`A · 严重`；保留说明 42。**页码**：第 8 页；**位置**：表 2。\n"
        "- **原文上下文**：温度 42℃\n- **影响**：边界判断不一致\n"
        "- **整改建议**：核查\n- **关联问题**：无",
    )

    normalized = audit_workflow._markdown(raw, "synthetic project")

    assert "### F-001001 [A] 实测问题（R10）" in normalized
    assert "#### F-001001" not in normalized
    for value in ("`R10`", "`A · 严重`", "保留说明 42。", "第 8 页", "表 2", "温度 42℃",
                  "边界判断不一致", "核查", "无"):
        assert value in normalized
    assert "- **等级**：`A · 严重`" in normalized
    assert "- **页码**：第 8 页" in normalized
    assert audit_workflow._check_project(normalized, 1, [], {"R10": "A"}) == ["F-001001"]

    from audit_delivery import _finding_context
    finding_block = normalized[normalized.index("### F-001001"):]
    page, quote = _finding_context(finding_block)
    assert page == 8
    assert quote == "温度 42℃"


def test_markdown_format_normalization_preserves_model_severity_judgment() -> None:
    raw = _project("6.1", "F-001001", ()).replace(
        "`A · 严重`", "`B · 主要`"
    )
    normalized = audit_workflow._markdown(raw, "synthetic project")
    assert "[A]" in normalized and "`B · 主要`" in normalized
    assert audit_workflow._check_project(normalized, 1, [], {"R10": "A"}) == ["F-001001"]


def test_bold_standalone_finding_titles_normalize_outside_fences_only() -> None:
    raw = (
        "# Report\n\n**F-000-001 [A] First global finding**\n\n"
        "**F-000-002 [B] Second global finding**\n\n"
        "**F-000-003 [A]**\n\n"
        "An ordinary bold reference **F-000-004 [A]** remains text.\n\n"
        "```markdown\n**F-000-005 [A] code sample**\n```\n"
    )
    normalized = audit_workflow._normalize_finding_markdown(raw)
    assert "### F-000-001 [A] First global finding" in normalized
    assert "### F-000-002 [B] Second global finding" in normalized
    assert "**F-000-003 [A]**" in normalized
    assert "An ordinary bold reference **F-000-004 [A]** remains text." in normalized
    assert "```markdown\n**F-000-005 [A] code sample**\n```" in normalized


@pytest.mark.parametrize("opening, closing", [
    ("```markdown", "```"), ("```md", "```"), ("```", "```"),
    ("```MARKDOWN", "```"), ("~~~md", "~~~"), ("~~~", "~~~"),
])
def test_project_markdown_accepts_common_outer_fences(opening: str, closing: str) -> None:
    raw = f"{opening}\n{_project('6.1', 'F-001001', ())}\n{closing}"
    normalized = audit_workflow._markdown(raw, "synthetic project")
    assert "## 项目 6.1 项目核查" in normalized
    assert audit_workflow._check_project(normalized, 1, []) == ["F-001001"]


@pytest.mark.parametrize("prefix", [" * ", " + ", "  - "])
def test_finding_metadata_list_prefix_is_normalized_for_delivery_parser(prefix: str) -> None:
    raw = _project("6.1", "F-001001", ()).replace(
        "问题详情。", f"{prefix}**页码**：第 8 页；**原文上下文**：温度 42℃\n"
    )
    normalized = audit_workflow._markdown(raw, "synthetic project")
    finding_block = normalized[normalized.index("### F-001001"):]

    from audit_delivery import _finding_context_data
    pages, quote = _finding_context_data(finding_block)
    assert pages == [(8, 8)]
    assert quote == "温度 42℃"
    assert "\n- **页码**：第 8 页" in finding_block
    assert "\n- **原文上下文**：温度 42℃" in finding_block


def test_global_rejects_wrong_finding_heading_level(monkeypatch: pytest.MonkeyPatch) -> None:
    from run_document_audit import validate_markdown as original_validate

    monkeypatch.setattr("run_document_audit.validate_markdown", lambda text, **kwargs: text)
    report = "# 审核报告\n## 全局问题\n#### F-000001 [B] 问题\n正文。"
    with pytest.raises(ValueError, match=r"exactly three #.*###"):
        audit_workflow._check_global(report, [])
    monkeypatch.setattr("run_document_audit.validate_markdown", original_validate)


def test_project_severity_metadata_is_preserved_without_local_business_gate():
    markdown = _project("6.1", "F-001001", ()).replace(
        "[A] 核查说明（R10）", "[B] 核查说明（R10）"
    ).replace("问题详情。", "- **等级**：`B · 主要`\n问题详情。")
    assert audit_workflow._check_project(markdown, 1, [], {"R10": "A"}) == ["F-001001"]

    correct = markdown.replace("[B]", "[A]").replace("`B · 主要`", "`A · 严重`")
    assert audit_workflow._check_project(correct, 1, [], {"R10": "A"}) == ["F-001001"]

    title_only = correct.replace("- **等级**：`A · 严重`\n", "")
    detail_only = correct.replace("[A] 核查说明（R10）", "核查说明（R10）")
    assert audit_workflow._check_project(title_only, 1, [], {"R10": "A"}) == ["F-001001"]
    assert audit_workflow._check_project(detail_only, 1, [], {"R10": "A"}) == ["F-001001"]


@pytest.mark.asyncio
async def test_project_severity_mismatch_reaches_final_llm_without_rewriting_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_builders(monkeypatch)
    index = json.dumps({"projects": [{"id": "6.1", "title": "存储", "page_start": 1, "page_end": 1}],
                        "no_projects_reason": ""}, ensure_ascii=False)
    project = _project("6.1", "F-001001", ()).replace(
        "[A] 核查说明（R10）", "[B] 核查说明（R10）"
    ).replace("`A · 严重`", "`B · 主要`")
    requests: list[str] = []

    async def submit(prompt: str) -> str:
        requests.append(prompt)
        if prompt.startswith("INDEX"):
            return index
        if prompt.startswith("PROJECT"):
            return project
        return _summary()

    report = "## Page 1\n报告内容。"
    await audit_workflow.execute_audit(report, [], 1, submit, tmp_path)
    assert len(requests) == 3
    assert "F-001001 [B]" in requests[-1]
    assert "`B · 主要`" in requests[-1]
    assert (tmp_path / "projects" / "001-raw.md").read_text(encoding="utf-8") == project


def test_finding_id_sequences_need_uniqueness_not_consecutive_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    from run_document_audit import validate_markdown as original_validate

    monkeypatch.setattr("run_document_audit.validate_markdown", lambda text, **kwargs: text)
    project = _project("6.1", "F-001007", ())
    assert audit_workflow._check_project(project, 1, []) == ["F-001007"]
    global_report = "# Report\n## Global\n### F-000009 [B] Finding\nDetails."
    assert audit_workflow._check_global(global_report, [])
    monkeypatch.setattr("run_document_audit.validate_markdown", original_validate)


def test_global_coverage_ignores_local_appendix_tables_but_requires_main_rows() -> None:
    from _rules import load_rules

    main_rows = "\n".join(
        f"| {rule} | 模块 | 检查项 | A | 通过 | 主报告依据 |" for rule in load_rules().ids
    )
    appendix = "\n".join([
        "## 附录：项目局部对照表",
        "| 规则 | 局部结果 |",
        "| --- | --- |",
        "| R10 | 项目局部说明 |",
    ])
    report = f"# 审核报告\n\n## 5. 检查覆盖表（内置规则）\n{main_rows}\n\n{appendix}"
    assert validate_markdown(report) == report

    incomplete = main_rows.replace("| R10 | 模块 | 检查项 | A | 通过 | 主报告依据 |\n", "")
    with pytest.raises(ValueError, match="R10"):
        validate_markdown(f"# 审核报告\n\n## 5. 检查覆盖表（内置规则）\n{incomplete}\n\n{appendix}")


def test_output_metadata_severity_is_not_rewritten_or_locally_rejected():
    report = _summary().replace("[B] 全局问题（R01）", "[A] 全局问题（R01）").replace(
        "### F-000001 [A] 全局问题（R01）\n- **规则号**：`R01`\n- **等级**：`B · 主要`",
        "### F-000001 [A] 全局问题（R01）\n- **规则号**：`R01`\n- **等级**：`A · 严重`",
    )
    assert validate_markdown(report) == report
    assert validate_markdown(report, rule_severities={"R01": "B"}) == report

    corrected = report.replace("[A] 全局问题", "[B] 全局问题").replace("`A · 严重`", "`B · 主要`")
    assert validate_markdown(corrected, rule_severities={"R01": "B"}) == corrected


def test_output_metadata_uses_enabled_extension_rule_ids_from_loaded_map():
    body = (
        "# 审核报告\n## 项目问题\n"
        "### F-000001 [A] 扩展规则发现（X01）\n"
        "- **规则号**：`X01`\n- **等级**：`A · 严重`\n"
        "证据说明用于校验等级元数据的基础格式，不包含任何业务推断或自动修正。\n"
    )
    assert validate_markdown(body, required_rule_ids=[], rule_severities={"X01": "B"}) == body.strip()
    corrected = body.replace("[A]", "[B]").replace("`A · 严重`", "`B · 主要`")
    assert validate_markdown(corrected, required_rule_ids=[], rule_severities={"X01": "B"}) == corrected.strip()

    # Rule references remain structurally accepted; severity reconciliation is
    # left to the final language-model summary.
    conflict = corrected.replace("`X01`", "`R14`")
    assert validate_markdown(conflict, required_rule_ids=[],
                              rule_severities={"X01": "B", "R14": "A"}) == conflict.strip()


async def _record(events: list[dict], event: dict) -> None:
    events.append(event)


@pytest.mark.asyncio
async def test_empty_project_index_requires_reason_and_still_runs_global_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_builders(monkeypatch)
    responses = iter([
        '{"projects":[],"no_projects_reason":"报告没有独立检测项目"}',
        _summary(),
    ])
    prompts: list[str] = []

    async def submit(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    result = await audit_workflow.execute_audit(
        "## Page 1\n全文", [], 1, submit, tmp_path
    )
    assert result.startswith("# 审核报告")
    assert len(prompts) == 2
    assert "没有独立检测项目" in json.loads(
        (tmp_path / "index.json").read_text(encoding="utf-8")
    )["no_projects_reason"]
    assert json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))["summary"]["status"] == "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "index_response",
    [
        '{"projects":[{"id":"6.1","title":"A","page_start":0,"page_end":1}],"no_projects_reason":""}',
        '{"projects":[{"id":"6.1","title":"A","page_start":1,"page_end":1},{"id":"6.1","title":"B","page_start":1,"page_end":1}],"no_projects_reason":""}',
        '{"projects":[],"no_projects_reason":""}',
    ],
)
async def test_invalid_index_after_one_correction_stops_without_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, index_response: str
) -> None:
    _install_builders(monkeypatch)
    calls = 0

    async def submit(prompt: str) -> str:
        nonlocal calls
        calls += 1
        return index_response

    with pytest.raises(ValueError):
        await audit_workflow.execute_audit("## Page 1\nbody", [], 1, submit, tmp_path)
    assert calls == 2
    assert not (tmp_path / "audit.md").exists()
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    assert manifest["index"]["status"] == "failed"
    assert (tmp_path / "index-raw.txt").is_file()
    assert (tmp_path / "index-retry-raw.txt").is_file()


@pytest.mark.asyncio
async def test_bad_project_response_retries_then_prevents_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_builders(monkeypatch)
    index = '{"projects":[{"id":"6.1","title":"A","page_start":1,"page_end":1}],"no_projects_reason":""}'
    bad = _project("6.1", "F-001001", ("台账.xlsx",)).replace("### 核查依据", "### 错误依据")
    async_calls = 0
    prompts: list[str] = []

    async def submit(prompt: str) -> str:
        nonlocal async_calls
        async_calls += 1
        prompts.append(prompt)
        if prompt.startswith("INDEX"):
            return index
        return bad

    with pytest.raises(RuntimeError, match="project"):
        await audit_workflow.execute_audit(
            "## Page 1\nbody", [{"filename": "台账.xlsx", "content": "x"}],
            1, submit, tmp_path
        )
    assert async_calls == 3
    assert (tmp_path / "projects" / "001-raw.md").read_text(encoding="utf-8") == bad
    assert (tmp_path / "projects" / "001-retry-raw.md").read_text(encoding="utf-8") == bad
    assert "<PREVIOUS_PROJECT_REVIEW_RAW>" in prompts[2]
    assert bad in prompts[2]
    assert "F-001001" in prompts[2] and "M01" in prompts[2] and "台账.xlsx" in prompts[2]
    assert not (tmp_path / "audit.md").exists()


@pytest.mark.asyncio
async def test_global_format_retry_includes_previous_raw_without_losing_ids_or_material_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_builders(monkeypatch)
    no_projects = '{"projects":[],"no_projects_reason":"全文没有独立检测项目"}'
    first_summary = _summary().replace("| R01 | 模块 | 检查项 | B | 通过 | 证据 |\n", "")
    prompts: list[str] = []
    summary_calls = 0

    async def submit(prompt: str) -> str:
        nonlocal summary_calls
        prompts.append(prompt)
        if prompt.startswith("INDEX"):
            return no_projects
        summary_calls += 1
        return first_summary

    result = await audit_workflow.execute_audit(
        "## Page 1\n报告正文", [{"filename": "台账.xlsx", "kind": "ledger", "content": "M01来源"}],
        1, submit, tmp_path,
    )

    assert len([prompt for prompt in prompts if prompt.startswith("SUMMARY")]) == 1
    assert "报告未完成" in result
    assert "报告正文" in prompts[-1]
    assert "| R01 | 页码 | 页码连续完整 | C | 待复核 | 模型未提供此规则结论 |" in result
    assert "| R01 | 页码 | 页码连续完整 | C | 通过 | 证据 |" not in result
    assert "F-000001" in result and "M01" in prompts[-1] and "台账.xlsx" in prompts[-1]
    assert (tmp_path / "audit-main-raw.md").read_text(encoding="utf-8") == first_summary
    assert not (tmp_path / "audit-main-retry-raw.md").exists()


@pytest.mark.asyncio
async def test_duplicate_project_issue_id_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_builders(monkeypatch)
    index = '{"projects":[{"id":"6.1","title":"A","page_start":1,"page_end":1}],"no_projects_reason":""}'
    bad = _project("6.1", "F-001001", ("台账.xlsx",)).replace(
        "### F-001001 [A] 核查说明", "### F-001001 [A] 首项\n详情。\n### F-001001 [A] 重复项\n标题"
    )
    responses = iter([index, bad, bad])

    async def submit(prompt: str) -> str:
        return next(responses)

    with pytest.raises(RuntimeError, match="project"):
        await audit_workflow.execute_audit(
            "## Page 1\nbody", [{"filename": "台账.xlsx", "content": "x"}],
            1, submit, tmp_path
        )
    assert not (tmp_path / "audit.md").exists()


@pytest.mark.asyncio
async def test_missing_page_marker_is_a_technical_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_builders(monkeypatch)
    async def submit(prompt: str) -> str:
        return '{"projects":[{"id":"6.1","title":"A","page_start":2,"page_end":2}],"no_projects_reason":""}'

    with pytest.raises(ValueError, match="page"):
        await audit_workflow.execute_audit(
            "## Page 1\nonly page one", [], 1, submit, tmp_path
        )
    assert not (tmp_path / "audit.md").exists()


@pytest.mark.asyncio
async def test_cancellation_is_recorded_and_propagated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_builders(monkeypatch)

    async def submit(prompt: str) -> str:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await audit_workflow.execute_audit("## Page 1\nbody", [], 1, submit, tmp_path)
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "cancelled"
    assert manifest["requests"][0]["status"] == "cancelled"
    assert not (tmp_path / "audit.md").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("first_failure", ("incomplete", "empty"))
async def test_text_model_incomplete_request_retries_same_prompt_once_then_saves_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first_failure: str,
) -> None:
    _install_builders(monkeypatch)
    index, project, summary = _request_fixture()
    prompts: list[str] = []
    project_calls = 0

    async def submit(prompt: str) -> str:
        nonlocal project_calls
        prompts.append(prompt)
        if prompt.startswith("INDEX"):
            return index
        if prompt.startswith("PROJECT"):
            project_calls += 1
            if project_calls == 1:
                if first_failure == "empty":
                    return ""
                raise _CodedSubmitError("text_model_incomplete")
            return project
        assert prompt.startswith("SUMMARY")
        return summary

    result = await audit_workflow.execute_audit(
        "## Page 1\nreport", [{"filename": "设备台账.xlsx", "kind": "ledger", "content": "source"}],
        1, submit, tmp_path,
    )

    assert result.startswith("> 报告未完成：模型未提供部分候选处置结论")
    project_requests = [item for item in json.loads(
        (tmp_path / "workflow.json").read_text(encoding="utf-8")
    )["requests"] if item["stage"] == "project-review:6.1"]
    assert [item["attempt"] for item in project_requests] == [1, 2]
    assert [item["status"] for item in project_requests] == ["failed", "received"]
    assert project_requests[0]["prompt_sha256"] == project_requests[1]["prompt_sha256"]
    assert project_requests[0]["error_code"] == (
        "text_model_empty" if first_failure == "empty" else "text_model_incomplete"
    )
    assert "response_sha256" in project_requests[0] if first_failure == "empty" else "response_sha256" not in project_requests[0]
    assert project_requests[1]["response_sha256"] == hashlib.sha256(project.encode("utf-8")).hexdigest()
    project_prompts = [prompt for prompt in prompts if prompt.startswith("PROJECT")]
    assert len(project_prompts) == 2 and project_prompts[0] == project_prompts[1]
    assert (tmp_path / "projects" / "001-raw.md").read_text(encoding="utf-8") == project


@pytest.mark.asyncio
async def test_actual_technical_validation_reason_reaches_manifest_and_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_builders(monkeypatch)
    index, project, _ = _request_fixture()
    invalid = project.replace("### 数值核查", "### 未完成的正文")

    async def submit(prompt: str) -> str:
        if prompt.startswith("INDEX"):
            return index
        assert prompt.startswith("PROJECT")
        return invalid

    with pytest.raises(RuntimeError, match="missing section 数值核查"):
        await audit_workflow.execute_audit("## Page 1\nreport", [], 1, submit, tmp_path)
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    assert manifest["projects"][0]["error"] == "Project response is missing section 数值核查"
    assert all(attempt["error"] == manifest["projects"][0]["error"]
               for attempt in manifest["projects"][0]["attempts"])
    assert not (tmp_path / "audit.md").exists()


@pytest.mark.asyncio
async def test_two_incomplete_model_requests_fail_without_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_builders(monkeypatch)
    index, _, _ = _request_fixture()
    project_calls = 0

    async def submit(prompt: str) -> str:
        nonlocal project_calls
        if prompt.startswith("INDEX"):
            return index
        if prompt.startswith("PROJECT"):
            project_calls += 1
            raise _CodedSubmitError("text_model_incomplete")
        raise AssertionError("summary must not be requested after project failure")

    with pytest.raises(RuntimeError, match="project review failed"):
        await audit_workflow.execute_audit("## Page 1\nreport", [], 1, submit, tmp_path)

    assert project_calls == 2
    assert not (tmp_path / "audit.md").exists()
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    project_requests = [item for item in manifest["requests"] if item["stage"] == "project-review:6.1"]
    assert len(project_requests) == 2
    assert [item["status"] for item in project_requests] == ["failed", "failed"]
    assert [item["error_code"] for item in project_requests] == [
        "text_model_incomplete", "text_model_incomplete",
    ]


@pytest.mark.asyncio
async def test_nonretryable_submit_error_fails_without_second_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_builders(monkeypatch)
    index, _, _ = _request_fixture()
    project_calls = 0

    async def submit(prompt: str) -> str:
        nonlocal project_calls
        if prompt.startswith("INDEX"):
            return index
        if prompt.startswith("PROJECT"):
            project_calls += 1
            raise ValueError("unsupported request parameter")
        raise AssertionError("summary must not be requested after project failure")

    with pytest.raises(RuntimeError, match="project review failed"):
        await audit_workflow.execute_audit("## Page 1\nreport", [], 1, submit, tmp_path)

    assert project_calls == 1
    assert not (tmp_path / "audit.md").exists()
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    project_requests = [item for item in manifest["requests"] if item["stage"] == "project-review:6.1"]
    assert len(project_requests) == 1
    assert project_requests[0]["status"] == "failed"
    assert project_requests[0]["error_type"] == "ValueError"
    assert "error_code" not in project_requests[0]


def test_markdown_accepts_prose_before_real_project_headings_without_losing_it() -> None:
    # The production Qwen response began with this ordinary introductory sentence.
    intro = (
        "我已完整阅读项目 6.2（第 37–46 页）源文本、前置汇总页（第 1–18 页）、"
        "三份上传资料（M01/M02/M03）及五组视觉核查原始记录，并逐值复核了全部 6 张数据表与 9 台设备台账。"
        "以下为该项目完整审核 Markdown。"
    )
    raw = intro + "\n\n" + _project("6.2", "F-001001", ())

    markdown = audit_workflow._markdown(raw, "Project 6.2")
    assert markdown == raw.strip()
    assert markdown.startswith(intro)
    assert audit_workflow._check_project(markdown, 1, []) == ["F-001001"]


def test_markdown_still_rejects_plain_text_without_a_real_heading() -> None:
    with pytest.raises(ValueError, match="must be Markdown"):
        audit_workflow._markdown("我已完成审核。没有Markdown标题。", "Project")


@pytest.mark.asyncio
async def test_project_failure_cancels_all_sibling_project_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    never = asyncio.Event()
    sibling_started = asyncio.Event()
    sibling_cancelled = asyncio.Event()
    queued_started = asyncio.Event()
    summary_called = False
    projects = [
        {"id": "6.1", "title": "A", "page_start": 2, "page_end": 2},
        {"id": "6.2", "title": "B", "page_start": 3, "page_end": 3},
        {"id": "6.3", "title": "C", "page_start": 4, "page_end": 4},
    ]
    monkeypatch.setattr(
        audit_workflow,
        "_load_builders",
        lambda: (
            lambda report, count: "INDEX",
            lambda project, *args, **kwargs: f"PROJECT {project['id']}",
            lambda *args, **kwargs: "SUMMARY",
        ),
    )

    async def submit(prompt: str) -> str:
        nonlocal summary_called
        if prompt == "INDEX":
            return json.dumps({"projects": projects, "no_projects_reason": ""})
        if prompt == "PROJECT 6.1":
            await asyncio.sleep(0.03)
            raise RuntimeError("simulated model output-token-limit failure")
        if prompt == "PROJECT 6.2":
            sibling_started.set()
            try:
                await never.wait()
            finally:
                sibling_cancelled.set()
        if prompt == "PROJECT 6.3":
            queued_started.set()
            return _project("6.3", "F-003001", ())
        if prompt == "SUMMARY":
            summary_called = True
            return _summary()
        raise AssertionError(f"unexpected prompt: {prompt}")

    pages = "\n\n".join(f"## Page {number}\npage {number}" for number in range(1, 5))
    with pytest.raises(RuntimeError, match="project review failed"):
        await audit_workflow.execute_audit(pages, [], 4, submit, tmp_path)

    assert sibling_started.is_set()
    assert sibling_cancelled.is_set()
    assert queued_started.is_set()
    assert not summary_called
    manifest = json.loads((tmp_path / "workflow.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["summary"]["status"] == "skipped"
    assert [item["status"] for item in manifest["projects"]] == ["failed", "cancelled", "complete"]
    assert "simulated model output-token-limit failure" not in (tmp_path / "workflow.json").read_text(encoding="utf-8")

def test_unbounded_finding_ids_support_large_project_and_sequence_numbers(monkeypatch):
    from audit_workflow import _check_project, _check_global

    first = _project("6.1", "F-1000-001", ())
    repeated = "\n".join(
        f"### F-1000-{sequence:03d} [A] finding {sequence}（R10）\n详情。"
        for sequence in range(2, 1002)
    )
    markdown = first + "\n" + repeated
    identifiers = _check_project(markdown, 1000, [])
    assert len(identifiers) == 1001
    assert identifiers[0] == "F-1000-001"
    assert identifiers[-1] == "F-1000-1001"
    assert _check_project(_project("6.1", "F-001-001", ()), 1, []) == ["F-001-001"]
    assert identifiers[0] != "F-001-1000"

    monkeypatch.setattr("run_document_audit.validate_markdown", lambda text, **kwargs: text)
    global_report = "# Report\n## Global\n" + "\n".join(
        f"### F-000-{sequence:03d} [A] finding {sequence}（R01）\n详情。"
        for sequence in range(1, 1002)
    )
    normalized = _check_global(global_report, [])
    assert "### F-000-1001 [A]" in normalized


def test_legacy_six_digit_project_and_global_ids_remain_accepted(monkeypatch):
    from audit_workflow import _check_project, _check_global

    assert _check_project(_project("6.1", "F-001001", ()), 1, []) == ["F-001001"]
    monkeypatch.setattr("run_document_audit.validate_markdown", lambda text, **kwargs: text)
    assert _check_global("# Report\n## Global\n### F-000001 [A] one\n详情。", [])
    assert _check_global("# Report\n## Global\n### F-0-1 [A] one\n详情。", [])


def test_global_coverage_accepts_and_preserves_qualified_model_results() -> None:
    markdown = (
        "# 审核报告\n**总评：需补充材料**\n\n## 检查覆盖表\n"
        "| # | 模块 | 检查项 | 等级 | 结果 | 证据位置/说明 |\n| --- | --- | --- | --- | --- | --- |\n"
        "| R07 | 标准 | 年代号 | B | 通过（仅年代号形式） | 未提供标准正文，不表示条款符合 |\n"
        "| R13 | 日期 | 日期链 | A | 通过（已读日期） | 生产日期为N/A，保留证据限制 |\n"
    )
    normalized = audit_workflow._check_global(markdown, ["R07", "R13"])
    assert "报告未完成" not in normalized
    assert "**总评：需补充材料**" in normalized
    assert "| R07 | 标准 | 年代号 | B | 通过（仅年代号形式） | 未提供标准正文，不表示条款符合 |" in normalized
    assert "| R13 | 日期 | 日期链 | A | 通过（已读日期） | 生产日期为N/A，保留证据限制 |" in normalized


def test_global_repeated_project_detail_is_preserved_as_reference_without_id_collision():
    markdown = (
        "# 审核报告\n**总评：不通过**\n\n"
        "### F-001-001 [B] 已有项目问题\n- **原文上下文**：逐字证据。\n"
        "### F-000-001 [C] 全局新问题\n- **原文上下文**：其他证据。\n"
    )
    normalized = audit_workflow._check_global(markdown, [], project_finding_ids={"F-001-001"})
    assert "**分项问题复核：F-001-001 [B] 已有项目问题**" in normalized
    assert "- **原文上下文**：逐字证据。" in normalized
    assert "### F-000-001 [C] 全局新问题" in normalized


def test_global_final_table_marks_missing_project_candidate_pending_without_blocking():
    markdown = (
        "# 审核报告\n**总评：不通过**\n\n"
        "| FID | 复核结果 | 最终等级 | 理由/依据 |\n|---|---|---|---|\n"
        "| F-001-001 | 成立 | B | 已确认 |\n"
    )
    normalized = audit_workflow._check_global(markdown, [], project_finding_ids={"F-001-001", "F-001-002"})
    assert "| F-001-001 | 成立 | B | 已确认 |" in normalized
    assert "| F-001-002 | 待复核 | — | 模型未给出明确处置；保留待复核，不推断成立或撤回。 |" in normalized
    assert "报告未完成：模型未提供部分候选处置结论" in normalized
    assert "F-001-002" in normalized


def test_global_new_table_finding_requires_its_detail_for_evidence_capture():
    markdown = (
        "# 审核报告\n**总评：不通过**\n\n"
        "| FID | 复核结果 | 最终等级 | 理由/依据 |\n|---|---|---|---|\n"
        "| F-000-001 | 成立 | B | 新问题，但未提供详情和原文 |\n"
    )
    with pytest.raises(ValueError, match="without detailed evidence.*F-000-001"):
        audit_workflow._check_global(markdown, [], project_finding_ids=set())


def test_format_retry_uses_external_template_and_preserves_opaque_source(tmp_path, monkeypatch):
    import audit_project_prompts
    (tmp_path / "format-retry.md").write_text("{{STAGE}}|{{ERROR}}|{{RAW}}|{{TAG}}\n", encoding="utf-8")
    monkeypatch.setattr(audit_project_prompts, "PROMPT_TEMPLATE_DIR", tmp_path)
    assert audit_workflow._format_retry_prompt("BASE", "{{RAW}}", "source${x}{y}", "summary") == (
        "BASE\n\nsummary|{{RAW}}|source${x}{y}|SUMMARY"
    )
