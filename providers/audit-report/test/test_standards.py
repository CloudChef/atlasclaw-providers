# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Shared standards library: storage location and rule-pack compilation."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import batch_audit  # noqa: E402
import standards_service  # noqa: E402

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
    return SimpleNamespace(data_dir=str(data_dir))


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
        sha256="0" * 64,
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
