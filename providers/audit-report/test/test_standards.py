# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Shared standards library: storage location and rule-pack compilation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import threading

from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import batch_audit  # noqa: E402
import standards_service  # noqa: E402


def _create_excel(host: SimpleNamespace, standard_id: str, file_name: str, *, kind_status: str | None = None) -> dict:
    from openpyxl import Workbook

    directory = standards_service.standard_dir(host, standard_id)
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "original.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "仪器"
    sheet.append(["序号", "设备编号", "校准日期"])
    sheet.append([1, "0007", "2026-01-02"])
    workbook.save(source)
    record = standards_service.create_standard(
        host, standard_id=standard_id, file_name=file_name, file_path=source,
        extension=".xlsx", size=source.stat().st_size,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(), pages=None, uploader="alice",
    )
    if kind_status:
        standards_service.update_standard(host, standard_id, status=kind_status)
    return record

RULE_DOC = """
# 客户审核要求

| 规则ID | 模块 | 检查项 | 不通过条件 | 建议等级 | 取证位置 |
| --- | --- | --- | --- | --- | --- |
| X01 | 客户要求 | 温度曲线 | 未附试验箱温度曲线原始记录 | B | 试验记录页 |
| X02 | 客户要求 | 分包实验室 | 有分包但未注明分包实验室名称和资质 | B | 声明页 |
"""


def _host(tmp_path: Path) -> SimpleNamespace:
    data_dir = tmp_path / "workspace" / ".provider-data" / "audit-report" / "default" / "alice"
    data_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(data_dir=str(data_dir), shared_data_dir=data_dir.parents[1] / "_shared")


def _create(host: SimpleNamespace, standard_id: str = "std-1") -> dict:
    directory = standards_service.standard_dir(host, standard_id)
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "original.md"
    source.write_text(RULE_DOC, encoding="utf-8")
    return standards_service.create_standard(
        host,
        standard_id=standard_id,
        file_name="客户审核要求.md",
        file_path=source,
        extension=".md",
        size=source.stat().st_size,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        pages=None,
        uploader="alice",
    )


def test_shared_root_is_outside_the_user_directory(tmp_path: Path) -> None:
    host = _host(tmp_path)

    shared = standards_service.shared_root(host)
    rules = standards_service.rules_root(host)

    assert "_shared" in shared.parts
    assert "alice" not in shared.parts
    assert "default" not in shared.parts
    assert rules.parent == shared


def test_configured_shared_root_contains_standards_and_builtin_rules(tmp_path: Path) -> None:
    host = _host(tmp_path)
    configured = tmp_path / "configured-standards"
    host.config = {"standards_dir": str(configured)}

    assert standards_service.shared_root(host) == configured
    standard = standards_service.standard_dir(host, "shared-id")
    assert standard == configured / "standards" / "shared-id"
    config_path = standards_service.ensure_rules_config(host)
    rules = configured / "rules"
    assert config_path == rules / "config.json"
    payload = standards_service.read_json(config_path)
    builtin = Path(payload["builtin"])
    assert builtin == rules / "builtin" / "rules.json"
    assert builtin.is_file()


def test_configured_builtin_is_not_overwritten(tmp_path: Path) -> None:
    host = _host(tmp_path)
    configured = tmp_path / "configured-standards"
    host.config = {"standards_dir": str(configured)}
    builtin = configured / "rules" / "builtin" / "rules.json"
    builtin.parent.mkdir(parents=True)
    builtin.write_text('{"rules":[],"custom":true}', encoding="utf-8")

    config_path = standards_service.ensure_rules_config(host)
    assert builtin.read_text(encoding="utf-8") == '{"rules":[],"custom":true}'
    assert Path(standards_service.read_json(config_path)["builtin"]) == builtin.resolve()


def test_configured_library_repoints_bundled_builtin_without_losing_config(tmp_path: Path) -> None:
    host = _host(tmp_path)
    configured = tmp_path / "configured-standards"
    host.config = {"standards_dir": str(configured)}
    rules = configured / "rules"
    rules.mkdir(parents=True)
    bundled = standards_service.skill_root() / "rules" / "builtin" / "rules.json"
    config_path = rules / "config.json"
    standards_service.write_json(config_path, {
        "version": 1, "builtin": str(bundled.resolve()), "packs": ["packs/custom"],
        "allow_overrides": True,
    })

    standards_service.ensure_rules_config(host)

    updated = standards_service.read_json(config_path)
    assert Path(updated["builtin"]) == rules / "builtin" / "rules.json"
    assert updated["packs"] == ["packs/custom"]
    assert updated["allow_overrides"] is True
    assert (rules / "builtin" / "rules.json").is_file()


def test_configured_library_preserves_custom_builtin_pointer(tmp_path: Path) -> None:
    host = _host(tmp_path)
    configured = tmp_path / "configured-standards"
    host.config = {"standards_dir": str(configured)}
    rules = configured / "rules"
    rules.mkdir(parents=True)
    custom = tmp_path / "external-custom-rules.json"
    custom.write_text('{"rules":[],"custom":true}', encoding="utf-8")
    config_path = rules / "config.json"
    standards_service.write_json(config_path, {"version": 1, "builtin": str(custom), "packs": []})

    standards_service.ensure_rules_config(host)

    assert standards_service.read_json(config_path)["builtin"] == str(custom)
    assert (rules / "builtin" / "rules.json").is_file()


def test_new_shared_material_starts_uploaded_with_separate_read_state(tmp_path: Path) -> None:
    host = _host(tmp_path)
    record = _create(host)
    assert record["status"] == standards_service.STATUS_UPLOADED
    assert record["read_status"] == standards_service.READ_READING
    assert record["kind"] == "supplement"


def test_legacy_compile_process_has_no_fixed_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Process:
        returncode = 0

        async def communicate(self):
            return b"completed", None

    process = Process()

    async def create_process(*_args, **_kwargs):
        return process

    async def forbidden_wait_for(*_args, **_kwargs):
        raise AssertionError("legacy compile process must not add a fixed deadline")

    monkeypatch.setattr(standards_service.asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(standards_service.asyncio, "wait_for", forbidden_wait_for)
    code, output = asyncio.run(standards_service._run(["synthetic"], cwd=tmp_path))

    assert code == 0 and output == "completed"


def test_legacy_compile_process_cancellation_still_kills_child(monkeypatch: pytest.MonkeyPatch,
                                                               tmp_path: Path) -> None:
    class Process:
        returncode = None
        calls = 0
        killed = False

        async def communicate(self):
            self.calls += 1
            if self.calls == 1:
                raise asyncio.CancelledError()
            return b"", None

        def kill(self):
            self.killed = True
            self.returncode = -9

    process = Process()

    async def create_process(*_args, **_kwargs):
        return process

    monkeypatch.setattr(standards_service.asyncio, "create_subprocess_exec", create_process)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(standards_service._run(["synthetic"], cwd=tmp_path))
    assert process.killed and process.calls == 2


def test_compile_standard_activates_rule_pack(tmp_path: Path) -> None:
    host = _host(tmp_path)
    _create(host)

    asyncio.run(standards_service.compile_standard(host, "std-1"))

    record = standards_service.get_standard(host, "std-1")
    assert record is not None
    assert record["status"] == "active", record.get("error_message")
    assert record["rules"] == 2
    assert record["pack"]

    config = json.loads((standards_service.rules_root(host) / "config.json").read_text(encoding="utf-8"))
    assert config["packs"] == [f"packs/{record['pack']}"]

    rules, packs = batch_audit.load_rule_set(ROOT / "skills" / "audit-report", rules_dir=standards_service.rules_root(host))
    ids = [rule.rule_id for rule in rules]
    assert "R01" in ids and "X01" in ids and "X02" in ids
    assert len(ids) == 21
    assert any(pack.startswith(record["pack"]) for pack in packs)


def test_compile_keeps_activated_pack_when_record_update_fails(tmp_path: Path, monkeypatch) -> None:
    host = _host(tmp_path)
    _create(host)
    original_update = standards_service.update_standard

    def fail_activation(host_arg, standard_id, **fields):
        if fields.get("status") == standards_service.STATUS_ACTIVE:
            raise OSError("record update failed")
        return original_update(host_arg, standard_id, **fields)

    monkeypatch.setattr(standards_service, "update_standard", fail_activation)
    with pytest.raises(OSError, match="record update failed"):
        asyncio.run(standards_service.compile_standard(host, "std-1"))

    config = standards_service.read_json(standards_service.rules_root(host) / "config.json")
    assert len(config["packs"]) == 1
    pack_path = standards_service.rules_root(host) / config["packs"][0] / "pack.json"
    assert pack_path.is_file()
    assert standards_service.read_json(pack_path)["status"] == standards_service.STATUS_ACTIVE


def test_delete_standard_removes_pack_and_config_entry(tmp_path: Path) -> None:
    host = _host(tmp_path)
    _create(host)
    asyncio.run(standards_service.compile_standard(host, "std-1"))
    pack = standards_service.get_standard(host, "std-1")["pack"]

    assert standards_service.delete_standard(host, "std-1") is True

    config = json.loads((standards_service.rules_root(host) / "config.json").read_text(encoding="utf-8"))
    assert config["packs"] == []
    assert not (standards_service.rules_root(host) / "packs" / pack).exists()
    assert standards_service.list_standards(host) == []


def test_same_name_standards_keep_independent_packs(tmp_path: Path) -> None:
    host = _host(tmp_path)
    _create(host, "std-1")
    second = _create(host, "std-2")
    Path(second["file_path"]).write_text(RULE_DOC.replace("X01", "X03").replace("X02", "X04"), encoding="utf-8")

    async def compile_both() -> None:
        await asyncio.gather(*(standards_service.compile_standard(host, key) for key in ("std-1", "std-2")))

    asyncio.run(compile_both())
    first = standards_service.get_standard(host, "std-1")
    second = standards_service.get_standard(host, "std-2")
    assert first["status"] == second["status"] == "active"
    assert first["pack"] != second["pack"]
    assert standards_service.delete_standard(host, "std-1")
    rules, _ = batch_audit.load_rule_set(ROOT / "skills" / "audit-report", rules_dir=standards_service.rules_root(host))
    ids = {rule.rule_id for rule in rules}
    assert {"X03", "X04"} <= ids
    assert not {"X01", "X02"} & ids


def test_failed_recompile_and_legacy_reference_preserve_active_pack(tmp_path: Path) -> None:
    host = _host(tmp_path)
    first = _create(host, "std-1")
    asyncio.run(standards_service.compile_standard(host, "std-1"))
    pack = standards_service.get_standard(host, "std-1")["pack"]

    Path(first["file_path"]).write_text("# No rules", encoding="utf-8")
    asyncio.run(standards_service.compile_standard(host, "std-1"))
    first = standards_service.get_standard(host, "std-1")
    assert first["status"] == "failed"
    assert first["pack"] == pack
    assert "X01" in {rule.rule_id for rule in standards_service.load_audit_rules(host)[0]}

    _create(host, "legacy")
    standards_service.update_standard(host, "legacy", status="active", pack=pack)
    assert standards_service.delete_standard(host, "std-1")
    assert "X01" in {rule.rule_id for rule in standards_service.load_audit_rules(host)[0]}
    assert standards_service.delete_standard(host, "legacy")
    assert "X01" not in {rule.rule_id for rule in standards_service.load_audit_rules(host)[0]}


def test_unparsable_document_is_reported_as_failed(tmp_path: Path) -> None:
    host = _host(tmp_path)
    directory = standards_service.standard_dir(host, "std-bad")
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "original.md"
    source.write_text("# 普通标准\n\n这里没有任何规则表。", encoding="utf-8")
    standards_service.create_standard(
        host,
        standard_id="std-bad",
        file_name="普通标准.md",
        file_path=source,
        extension=".md",
        size=source.stat().st_size,
        sha256="0" * 64,
        pages=None,
        uploader="alice",
    )

    asyncio.run(standards_service.compile_standard(host, "std-bad"))

    record = standards_service.get_standard(host, "std-bad")
    assert record["status"] == "failed"
    assert record["error_message"]
    assert record["pack"] == ""


def test_material_classification_and_prepare_excel_are_independent_of_compile_status(tmp_path: Path) -> None:
    host = _host(tmp_path)
    record = _create_excel(host, "excel-1", "检测标准与设备台账.xlsx", kind_status="failed")

    assert standards_service.classify_material("检测标准与设备台账.xlsx") == "ledger"
    assert standards_service.classify_material("客户检测标准.xlsx") == "standard"
    assert standards_service.classify_material("随附照片.xlsx") == "supplement"
    assert record["read_status"] == "reading"
    read_record = asyncio.run(standards_service.prepare_standard(host, "excel-1"))
    assert read_record["status"] == "failed"  # Legacy compile failure is kept separate.
    assert read_record["read_status"] == "ready"
    assert read_record["kind"] == "ledger"
    assert read_record["read_characters"] > 0
    assert read_record["source_position_count"] == 2


def test_prepare_standard_keeps_event_loop_responsive_while_library_lock_is_held(tmp_path: Path) -> None:
    host = _host(tmp_path)
    _create_excel(host, "locked", "检测标准台账.xlsx")
    entered = threading.Event()
    release = threading.Event()
    heartbeat_ticks = [0]
    ticks_when_released = [0]

    def hold_lock() -> None:
        with standards_service._LIBRARY_LOCK:
            entered.set()
            release.wait(1)
            ticks_when_released[0] = heartbeat_ticks[0]

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert entered.wait(1)

    async def exercise() -> None:
        async def heartbeat() -> None:
            while heartbeat_ticks[0] < 3:
                heartbeat_ticks[0] += 1
                await asyncio.sleep(0)
            release.set()

        await asyncio.gather(standards_service.prepare_standard(host, "locked"), heartbeat())

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        holder.join(timeout=2)

    assert ticks_when_released[0] >= 3


def test_snapshot_includes_old_failed_and_duplicate_names_without_overwrite(tmp_path: Path) -> None:
    host = _host(tmp_path)
    first = _create_excel(host, "legacy-failed", "检测标准台账.xlsx", kind_status="failed")
    second = _create_excel(host, "another-id", "检测标准台账.xlsx", kind_status="failed")
    # Emulate a pre-read-state record that failed historical rule compilation.
    legacy_record = standards_service.get_standard(host, "legacy-failed")
    legacy_record.pop("read_status", None)
    legacy_record.pop("read_error", None)
    standards_service.write_json(standards_service.standard_dir(host, "legacy-failed") / "standard.json", legacy_record)

    destination = tmp_path / "runs" / "attempt-1"
    snapshot = standards_service.snapshot_audit_library(host, destination)

    assert [item["reference_id"] for item in snapshot["materials"]] == ["M01", "M02"]
    assert [item["standard_id"] for item in snapshot["materials"]] == ["another-id", "legacy-failed"]
    assert snapshot["material_paths"][0].name == snapshot["material_paths"][1].name == "检测标准台账.xlsx"
    assert snapshot["material_paths"][0] != snapshot["material_paths"][1]
    assert all(path.is_file() for path in snapshot["material_paths"])
    assert snapshot["materials"][0]["kind"] == "ledger"
    assert snapshot["rules_dir"].is_dir()
    private_config = json.loads((snapshot["rules_dir"] / "config.json").read_text(encoding="utf-8"))
    assert Path(private_config["builtin"]).is_absolute() is False

    # The attempt snapshot remains usable when shared records are deleted later.
    assert standards_service.delete_standard(host, "legacy-failed")
    assert all(path.is_file() for path in snapshot["material_paths"])
    from audit_materials import read_material
    assert all(read_material(path)["sha256"] == item["sha256"]
               for path, item in zip(snapshot["material_paths"], snapshot["materials"]))
    assert snapshot["materials"][1]["sha256"] == first["sha256"]
    assert snapshot["materials"][0]["sha256"] == second["sha256"]
    assert json.loads((destination / "audit-library-snapshot.json").read_text(encoding="utf-8"))["materials"][0]["reference_id"] == "M01"


def test_snapshot_rejects_missing_or_hash_changed_shared_material(tmp_path: Path) -> None:
    host = _host(tmp_path)
    record = _create_excel(host, "changed", "设备台账.xlsx")
    Path(record["file_path"]).write_bytes(b"changed after upload")

    try:
        standards_service.snapshot_audit_library(host, tmp_path / "run")
    except ValueError as exc:
        assert "hash differs" in str(exc)
    else:
        raise AssertionError("changed shared source must fail the snapshot")


def test_snapshot_fails_instead_of_skipping_invalid_record_json(tmp_path: Path) -> None:
    host = _host(tmp_path)
    _create_excel(host, "valid", "有效台账.xlsx")
    invalid_dir = standards_service.standard_dir(host, "broken-record")
    invalid_dir.mkdir(parents=True, exist_ok=True)
    (invalid_dir / "standard.json").write_text("{bad json", encoding="utf-8")

    try:
        standards_service.snapshot_audit_library(host, tmp_path / "run")
    except ValueError as exc:
        assert "broken-record/standard.json" in str(exc)
    else:
        raise AssertionError("invalid shared record JSON must fail the snapshot")


def test_snapshot_copies_enabled_rule_pack_without_mutating_shared_config(tmp_path: Path) -> None:
    host = _host(tmp_path)
    _create(host, "compiled")
    asyncio.run(standards_service.compile_standard(host, "compiled"))
    shared_config = json.loads((standards_service.rules_root(host) / "config.json").read_text(encoding="utf-8"))

    snapshot = standards_service.snapshot_audit_library(host, tmp_path / "run-private")

    private_config = json.loads((snapshot["rules_dir"] / "config.json").read_text(encoding="utf-8"))
    assert all(not Path(entry).is_absolute() for entry in private_config["packs"])
    private_rules, _ = batch_audit.load_rule_set(ROOT / "skills" / "audit-report", rules_dir=snapshot["rules_dir"])
    assert "X01" in {rule.rule_id for rule in private_rules}
    assert json.loads((standards_service.rules_root(host) / "config.json").read_text(encoding="utf-8")) == shared_config

    assert standards_service.delete_standard(host, "compiled")
    still_private, _ = batch_audit.load_rule_set(ROOT / "skills" / "audit-report", rules_dir=snapshot["rules_dir"])
    assert "X01" in {rule.rule_id for rule in still_private}


def test_prepare_bad_excel_sets_read_failed_without_changing_compile_fields(tmp_path: Path) -> None:
    host = _host(tmp_path)
    directory = standards_service.standard_dir(host, "bad-xlsx")
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "broken.xlsx"
    source.write_bytes(b"not an xlsx")
    record = standards_service.create_standard(
        host, standard_id="bad-xlsx", file_name="坏台账.xlsx", file_path=source,
        extension=".xlsx", size=source.stat().st_size,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(), pages=None, uploader="alice",
    )

    result = asyncio.run(standards_service.prepare_standard(host, "bad-xlsx"))

    assert result["read_status"] == "failed"
    assert result["read_error"]
    assert result["status"] == record["status"]
