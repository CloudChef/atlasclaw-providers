#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load and validate audit rule packs.

Directory contract (under the skill root)::

    rules/
    |-- config.json              enabled packs + override policy
    |-- builtin/rules.json       built-in rules (single source of truth)
    |-- builtin/source/          source workbook/document for the builtin rules
    |-- packs/<pack>/pack.json   compiled rule pack (data, never code)
    |-- packs/<pack>/source/     original rule document(s)
    `-- _inbox/                  rule documents waiting to be compiled

`check_coverage.py`, `verify_findings.py` and the prompt builders read rule ids
and severities from here, so adding or replacing rules never requires editing
Python. The built-in JSON is mandatory: a missing file is an error, never a
silent fallback to an older rule set.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SKILL_ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = SKILL_ROOT / "rules"

RULE_ID_RE = re.compile(r"^[A-Z]\d{2,}$")
PACK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
SEVERITIES = {"A", "B", "C"}
SCOPES = {"single", "batch"}
STAGES = {"global", "project"}
REQUIRES = {"text", "image", "standard", "ledger", "materials", "visual_model"}
CHECK_TYPES = {
    "page_sequence",
    "text_regex",
    "text_consistency",
    "numeric_range",
    "date_chain",
    "cross_page_merge",
    "cross_file",
    "visual",
    "manual",
    "python",
}


class RulesError(ValueError):
    """Raised when a rule pack is missing, malformed, or conflicts."""


@dataclass
class RuleSet:
    """Resolved rule packs for one audit run."""

    rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    packs: list[dict[str, Any]] = field(default_factory=list)
    skipped_drafts: list[str] = field(default_factory=list)
    builtin_ids: list[str] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        return list(self.rules)

    @property
    def extra_ids(self) -> list[str]:
        builtin = set(self.builtin_ids)
        return [rule_id for rule_id in self.rules if rule_id not in builtin]

    @property
    def severity(self) -> dict[str, str]:
        return {rule_id: rule["severity"] for rule_id, rule in self.rules.items()}

    def summary(self) -> str:
        parts = [f"{pack['pack']}@{pack['version']}" for pack in self.packs]
        return " + ".join(parts) if parts else "builtin"


def default_rules_dir() -> Path:
    """Return the rules directory, honouring AUDIT_RULES_DIR for tests."""
    override = os.environ.get("AUDIT_RULES_DIR")
    return Path(override).expanduser() if override else RULES_DIR


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RulesError(f"无法读取规则文件 {path}: {exc}") from exc
    except ValueError as exc:
        raise RulesError(f"规则文件不是合法 JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RulesError(f"规则文件顶层必须是对象: {path}")
    return payload


def load_pack(path: Path) -> dict[str, Any]:
    pack = read_json(path)
    pack.setdefault("status", "active")
    pack["_path"] = str(path)
    return pack


def load_config(root: Path) -> dict[str, Any]:
    path = root / "config.json"
    if not path.is_file():
        return {"version": 1, "builtin": "builtin/rules.json", "packs": [], "allow_overrides": False}
    return read_json(path)


def resolve_pack_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    if path.is_dir():
        path = path / "pack.json"
    return path


def load_rules(
    root: Path | None = None,
    extra: Iterable[str | Path] = (),
    *,
    include_drafts: bool = False,
) -> RuleSet:
    """Load builtin plus configured/extra packs.

    The builtin JSON is required. Pack order is builtin, then config.json order,
    then extra paths. Later packs may override an id only when the pack lists it
    in ``overrides`` and config has ``allow_overrides: true``.
    """
    root = Path(root) if root else default_rules_dir()
    config = load_config(root)
    allow_overrides = bool(config.get("allow_overrides", False))

    builtin_path = resolve_pack_path(root, config.get("builtin", "builtin/rules.json"))
    if not builtin_path.is_file() and str(config.get("builtin", "builtin/rules.json")) == "builtin/rules.json":
        # Packs may be snapshotted into a temporary library root without copying
        # the builtin JSON; use the skill's authoritative builtin in that case.
        fallback = default_rules_dir() / "builtin" / "rules.json"
        if fallback.is_file():
            builtin_path = fallback
    if not builtin_path.is_file():
        raise RulesError(f"内置规则 JSON 不存在: {builtin_path}")
    pack_paths: list[tuple[Path, bool]] = [(builtin_path, False)]
    for entry in config.get("packs", []):
        path = resolve_pack_path(root, str(entry))
        if not path.is_file():
            raise RulesError(f"config.json 启用的规则包不存在: {path}")
        pack_paths.append((path, False))
    for entry in extra:
        path = resolve_pack_path(root, str(entry))
        if not path.is_file():
            raise RulesError(f"--rules 指定的规则包不存在: {path}")
        pack_paths.append((path, True))

    ruleset = RuleSet()

    for path, explicit in pack_paths:
        pack = load_pack(path)
        status = pack.get("status", "active")
        is_builtin = path.resolve() == builtin_path.resolve()
        # Explicit --rules means the caller deliberately chose this pack, so a
        # draft is allowed there; config packs still require activation.
        if not explicit and not is_builtin and status != "active" and not include_drafts:
            ruleset.skipped_drafts.append(f"{pack.get('pack', path.parent.name)} ({status})")
            continue
        rules = pack.get("rules")
        if not isinstance(rules, list) or not rules:
            raise RulesError(f"规则包没有 rules: {path}")

        overrides = set(pack.get("overrides", []))
        for rule in rules:
            rule_id = str(rule.get("id", "")).strip()
            if not RULE_ID_RE.match(rule_id):
                raise RulesError(f"非法规则号 {rule_id!r} in {path}")
            if rule_id in ruleset.rules:
                if allow_overrides and rule_id in overrides:
                    ruleset.rules[rule_id] = dict(rule)
                    continue
                raise RulesError(
                    f"规则号 {rule_id} 在多个规则包中重复（{path}）；"
                    f"如需覆盖请在 pack.json 声明 overrides 并设置 allow_overrides=true"
                )
            ruleset.rules[rule_id] = dict(rule)

        if is_builtin:
            ruleset.builtin_ids = [str(rule.get("id", "")).strip() for rule in rules]
        ruleset.packs.append(
            {
                "pack": pack.get("pack", path.parent.name),
                "version": pack.get("version", "0.0.0"),
                "status": status,
                "path": str(path),
            }
        )

    if not ruleset.rules or not ruleset.builtin_ids:
        raise RulesError("内置规则集为空")
    return ruleset


def validate_pack(
    pack: dict[str, Any],
    pack_path: Path,
    builtin_ids: Iterable[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Validate one pack. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    name = str(pack.get("pack", "")).strip()
    if not name:
        errors.append("缺少 pack 名称")
    elif not PACK_NAME_RE.match(name):
        errors.append(f"pack 名称必须是小写字母/数字/连字符: {name!r}")

    version = str(pack.get("version", "")).strip()
    if not SEMVER_RE.match(version):
        errors.append(f"version 必须是语义化版本: {version!r}")

    status = pack.get("status", "active")
    if status not in {"draft", "active"}:
        errors.append(f"status 只能是 draft/active: {status!r}")

    if not str(pack.get("title", "")).strip():
        warnings.append("缺少 title，报告中将显示 pack 名称")

    rules = pack.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("rules 必须是非空数组")
        return errors, warnings

    builtin = set(builtin_ids or [])
    seen: set[str] = set()
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            errors.append(f"第 {index} 条规则不是对象")
            continue
        rule_id = str(rule.get("id", "")).strip()
        if not RULE_ID_RE.match(rule_id):
            errors.append(f"第 {index} 条规则号非法: {rule_id!r}（应为字母+至少两位数字，如 R01）")
        elif rule_id in seen:
            errors.append(f"规则号重复: {rule_id}")
        seen.add(rule_id)

        if name != "builtin" and builtin and rule_id in builtin:
            errors.append(f"附加规则不得占用内置规则号: {rule_id}")

        if rule.get("severity") not in SEVERITIES:
            errors.append(f"{rule_id}: severity 必须是 A/B/C")
        if not str(rule.get("title", "")).strip():
            errors.append(f"{rule_id}: 缺少 title")
        if not str(rule.get("fail_when", "")).strip():
            errors.append(f"{rule_id}: 缺少 fail_when（不通过条件）")
        if not str(rule.get("module", "")).strip():
            warnings.append(f"{rule_id}: 缺少 module，按“客户要求”处理")
        if rule.get("scope", "single") not in SCOPES:
            errors.append(f"{rule_id}: scope 只能是 single/batch")
        if rule.get("stage", "project") not in STAGES:
            errors.append(f"{rule_id}: stage 只能是 global/project")
        check = rule.get("check")
        if not isinstance(check, dict) or check.get("type") not in CHECK_TYPES:
            errors.append(f"{rule_id}: check.type 必须是 {sorted(CHECK_TYPES)} 之一")
        evidence = rule.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        if not evidence:
            warnings.append(f"{rule_id}: 缺少 evidence（取证位置）")
        requires = rule.get("requires", [])
        if isinstance(requires, str):
            requires = [requires]
        unknown = sorted(set(requires) - REQUIRES)
        if unknown:
            errors.append(f"{rule_id}: requires 含未知项 {unknown}")

    source = pack.get("compiled_from") or {}
    if source.get("source"):
        source_path = (pack_path.parent / source["source"]).resolve()
        if not source_path.is_file():
            warnings.append(f"compiled_from.source 不存在: {source_path}")
        else:
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if source.get("sha256") and digest != source["sha256"]:
                errors.append("规则文档已变更，pack.json 过期；请先运行 rules_sync.py 重新编译")

    return errors, warnings


def normalize_heading(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", "", value).strip().lower()
