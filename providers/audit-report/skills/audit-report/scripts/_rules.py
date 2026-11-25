#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load and validate audit rule packs.

Directory contract (under the skill root)::

    rules/
    |-- config.json              enabled packs + override policy
    |-- builtin/rules.json       19 built-in rules (single source of truth)
    |-- packs/<pack>/pack.json   compiled rule pack (data, never code)
    |-- packs/<pack>/source/     original rule document(s)
    `-- _inbox/                  rule documents waiting to be compiled

`check_coverage.py` and `verify_findings.py` read rule ids and severities
from here, so adding a rule never requires editing Python. When the builtin
JSON is missing the hard-coded fallback keeps the skill usable, but tests
assert that the JSON and the fallback agree.
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

RULE_ID_RE = re.compile(r"^[A-Z]\d{2}$")
PACK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
SEVERITIES = {"A", "B", "C"}
SCOPES = {"single", "batch"}
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
BUILTIN_IDS = [f"R{i:02d}" for i in range(1, 20)]

# Kept in sync with rules/builtin/rules.json; used only if that file is missing.
FALLBACK_SEVERITY = {
    "R01": "B", "R02": "A", "R03": "B", "R04": "B", "R05": "A",
    "R06": "A", "R07": "B", "R08": "B", "R09": "B", "R10": "A",
    "R11": "A", "R12": "A", "R13": "A", "R14": "A", "R15": "A",
    "R16": "B", "R17": "C", "R18": "C", "R19": "B",
}


class RulesError(ValueError):
    """Raised when a rule pack is missing, malformed, or conflicts."""


@dataclass
class RuleSet:
    """Resolved rule packs for one audit run."""

    rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    packs: list[dict[str, Any]] = field(default_factory=list)
    skipped_drafts: list[str] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        return list(self.rules)

    @property
    def builtin_ids(self) -> list[str]:
        return [rule_id for rule_id in self.rules if rule_id in BUILTIN_IDS]

    @property
    def extra_ids(self) -> list[str]:
        return [rule_id for rule_id in self.rules if rule_id not in BUILTIN_IDS]

    @property
    def severity(self) -> dict[str, str]:
        return {rule_id: rule["severity"] for rule_id, rule in self.rules.items()}

    def summary(self) -> str:
        parts = [f"{pack['pack']}@{pack['version']}" for pack in self.packs]
        return " + ".join(parts) if parts else "builtin(内置兜底)"


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


def fallback_builtin() -> dict[str, Any]:
    return {
        "pack": "builtin",
        "version": "0.0.0-fallback",
        "title": "内置 19 项（兜底）",
        "status": "active",
        "rules": [
            {"id": rule_id, "severity": severity, "title": rule_id, "module": "内置", "fail_when": ""}
            for rule_id, severity in FALLBACK_SEVERITY.items()
        ],
    }


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

    Pack order is builtin, then config.json order, then extra paths. Later
    packs may override an id only when the pack lists it in ``overrides`` and
    config has ``allow_overrides: true``.
    """
    root = Path(root) if root else default_rules_dir()
    config = load_config(root)
    allow_overrides = bool(config.get("allow_overrides", False))

    pack_paths: list[tuple[Path, bool]] = []
    builtin_path = resolve_pack_path(root, config.get("builtin", "builtin/rules.json"))
    if builtin_path.is_file():
        pack_paths.append((builtin_path, False))
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
        # Explicit --rules means the caller deliberately chose this pack, so a
        # draft is allowed there; config packs still require activation.
        if not explicit and status != "active" and not include_drafts:
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

        ruleset.packs.append(
            {
                "pack": pack.get("pack", path.parent.name),
                "version": pack.get("version", "0.0.0"),
                "status": status,
                "path": str(path),
            }
        )

    if not ruleset.rules:
        builtin = fallback_builtin()
        for rule in builtin["rules"]:
            ruleset.rules[rule["id"]] = rule
        ruleset.packs.append(
            {"pack": "builtin", "version": builtin["version"], "status": "active", "path": "(fallback)"}
        )
    return ruleset


def validate_pack(pack: dict[str, Any], pack_path: Path) -> tuple[list[str], list[str]]:
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

    seen: set[str] = set()
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            errors.append(f"第 {index} 条规则不是对象")
            continue
        rule_id = str(rule.get("id", "")).strip()
        if not RULE_ID_RE.match(rule_id):
            errors.append(f"第 {index} 条规则号非法: {rule_id!r}（应为字母+两位数字，如 X01）")
        elif rule_id in seen:
            errors.append(f"规则号重复: {rule_id}")
        seen.add(rule_id)

        if name != "builtin" and rule_id in BUILTIN_IDS:
            errors.append(f"附加规则不得占用内置规则号: {rule_id}")
        if name == "builtin" and rule_id not in BUILTIN_IDS:
            errors.append(f"内置规则包只能包含 R01–R19: {rule_id}")

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
        check = rule.get("check")
        if not isinstance(check, dict) or check.get("type") not in CHECK_TYPES:
            errors.append(f"{rule_id}: check.type 必须是 {sorted(CHECK_TYPES)} 之一")
        evidence = rule.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        if not evidence:
            warnings.append(f"{rule_id}: 缺少 evidence（取证位置）")

    if name == "builtin":
        missing = [rule_id for rule_id in BUILTIN_IDS if rule_id not in seen]
        if missing:
            errors.append("内置规则缺少: " + ", ".join(missing))

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
