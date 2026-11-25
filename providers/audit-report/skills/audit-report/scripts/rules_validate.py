#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate rule packs and optionally activate one.

Checks structure, ids, severities, scope, check type, duplicate ids, reserved
builtin ids, and whether ``compiled_from.sha256`` still matches the source
document. A pack must pass validation before it can be activated; activation
adds it to ``rules/config.json`` so audit scripts load it by default.

Usage:
    python rules_validate.py                       # validate builtin + all packs
    python rules_validate.py rules/packs/xy/pack.json
    python rules_validate.py rules/packs/xy/pack.json --activate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _rules import RULES_DIR, read_json, validate_pack


def collect_paths(rules_dir: Path, args: list[str]) -> list[Path]:
    if args:
        return [Path(raw) for raw in args]
    paths = []
    builtin = rules_dir / "builtin" / "rules.json"
    if builtin.is_file():
        paths.append(builtin)
    packs_dir = rules_dir / "packs"
    if packs_dir.is_dir():
        paths.extend(sorted(packs_dir.glob("*/pack.json")))
    return paths


def activate(pack_path: Path, rules_dir: Path) -> str:
    pack = read_json(pack_path)
    pack["status"] = "active"
    pack.pop("_path", None)
    pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    config_path = rules_dir / "config.json"
    config = read_json(config_path) if config_path.is_file() else {
        "version": 1, "builtin": "builtin/rules.json", "packs": [], "allow_overrides": False,
    }
    try:
        relative = pack_path.parent.relative_to(rules_dir).as_posix()
    except ValueError:
        relative = pack_path.as_posix()
    entries = list(config.get("packs", []))
    if relative not in entries:
        entries.append(relative)
    config["packs"] = entries
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return relative


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Validate audit rule packs.")
    parser.add_argument("paths", nargs="*", help="pack.json paths (default: builtin + all packs)")
    parser.add_argument("--rules-dir", default=str(RULES_DIR), help="Rules directory")
    parser.add_argument("--activate", action="store_true", help="Activate the validated pack and add it to config.json")
    parser.add_argument("--json", dest="json_out", help="Write validation result JSON")
    args = parser.parse_args()

    rules_dir = Path(args.rules_dir)
    paths = collect_paths(rules_dir, args.paths)
    if not paths:
        print("[ERROR] 未找到任何规则包", file=sys.stderr)
        return 2
    if args.activate and len(paths) != 1:
        print("[ERROR] --activate 一次只能启用一个规则包", file=sys.stderr)
        return 2

    report = []
    failed = False
    seen_rules: dict[str, tuple[str, str]] = {}
    for path in paths:
        if not path.is_file():
            print(f"[FAIL] {path}: 文件不存在")
            failed = True
            continue
        try:
            pack = read_json(path)
        except ValueError as exc:
            print(f"[FAIL] {path}: {exc}")
            failed = True
            continue
        errors, warnings = validate_pack(pack, path)
        pack_name = str(pack.get("pack", path.parent.name))
        pack_status = str(pack.get("status", "active"))
        for rule in pack.get("rules") or []:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("id") or "").strip()
            if not rule_id:
                continue
            previous = seen_rules.get(rule_id)
            if previous:
                previous_pack, previous_status = previous
                message = f"规则号 {rule_id} 与 {previous_pack} 重复"
                if previous_status == "active" and pack_status == "active":
                    errors.append(message + "；同时启用会冲突")
                else:
                    warnings.append(message + "（其中一个为 draft）")
            else:
                seen_rules[rule_id] = (pack_name, pack_status)
        report.append(
            {
                "pack": pack.get("pack", path.parent.name),
                "version": pack.get("version"),
                "status": pack.get("status", "active"),
                "path": str(path),
                "rules": len(pack.get("rules", [])),
                "errors": errors,
                "warnings": warnings,
            }
        )
        if errors:
            failed = True
            print(f"[FAIL] {path}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"[OK] {path}: {len(pack.get('rules', []))} rules")
        for warning in warnings:
            print(f"  [WARN] {warning}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"ok": not failed, "packs": report}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if args.activate and not failed:
        relative = activate(paths[0], rules_dir)
        print(f"[OK] activated {relative}; added to config.json")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
