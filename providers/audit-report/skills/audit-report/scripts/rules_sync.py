#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Synchronise rule documents with compiled rule packs.

This is the gate before an audit: a rule document that has no ``pack.json``,
or whose ``pack.json`` is older than the document, must be compiled before
the audit is allowed to continue.

Scans:
    rules/_inbox/*.md|.txt|.docx|.pdf     -> moved to packs/<slug>/source/, compiled
    rules/packs/<pack>/source/*           -> compiled when pack.json is missing or stale

Usage:
    python rules_sync.py                 # compile everything that is missing/stale
    python rules_sync.py --check         # report only, exit 1 when work is pending
    python rules_sync.py --rules-dir <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

from _rules import RULES_DIR, load_pack
from rules_compile import SUPPORTED_INPUTS, compile_pack, slugify


def is_rule_document(path: Path) -> bool:
    if path.suffix.lower() not in SUPPORTED_INPUTS:
        return False
    return path.stem.lower() not in {"readme", "index", "示例", "说明"}


def source_documents(pack_dir: Path) -> list[Path]:
    source_dir = pack_dir / "source"
    if not source_dir.is_dir():
        return []
    return sorted(path for path in source_dir.iterdir() if path.is_file() and is_rule_document(path))


def pack_prefix(pack_dir: Path) -> str:
    pack_path = pack_dir / "pack.json"
    if not pack_path.is_file():
        return "X"
    try:
        pack = load_pack(pack_path)
    except ValueError:
        return "X"
    for rule in pack.get("rules", []):
        rule_id = str(rule.get("id", ""))
        if rule_id[:1].isalpha():
            return rule_id[0]
    return "X"


def is_stale(pack_dir: Path, source: Path) -> bool:
    pack_path = pack_dir / "pack.json"
    if not pack_path.is_file():
        return True
    try:
        pack = load_pack(pack_path)
    except ValueError:
        return True
    compiled = (pack.get("compiled_from") or {}).get("sha256")
    if not compiled:
        return True
    return hashlib.sha256(source.read_bytes()).hexdigest() != compiled


def recompile(pack_dir: Path, source: Path) -> None:
    pack_path = pack_dir / "pack.json"
    title = ""
    version = "1.0.0"
    if pack_path.is_file():
        try:
            existing = load_pack(pack_path)
            title = existing.get("title", "")
            version = existing.get("version", "1.0.0")
        except ValueError:
            pass
    compile_pack(
        source,
        pack_dir.name,
        pack_dir,
        prefix=pack_prefix(pack_dir),
        title=title,
        version=version,
        copy_source=False,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Compile missing/stale rule documents into rule packs.")
    parser.add_argument("--rules-dir", default=str(RULES_DIR), help="Rules directory (default: skill rules/)")
    parser.add_argument("--check", action="store_true", help="Report pending work and exit 1; do not compile")
    args = parser.parse_args()

    rules_dir = Path(args.rules_dir)
    packs_dir = rules_dir / "packs"
    inbox = rules_dir / "_inbox"
    pending: list[str] = []
    done: list[str] = []

    inbox_docs: list[Path] = []
    if inbox.is_dir():
        inbox_docs = sorted(
            path for path in inbox.iterdir() if path.is_file() and is_rule_document(path)
        )

    for document in inbox_docs:
        slug = slugify(document.stem)
        pack_dir = packs_dir / slug
        suffix = 2
        while pack_dir.exists():
            pack_dir = packs_dir / f"{slug}-{suffix}"
            suffix += 1
        if args.check:
            pending.append(f"{document.name} -> {pack_dir.relative_to(rules_dir)} (未编译)")
            continue
        source_dir = pack_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        target = source_dir / document.name
        shutil.move(str(document), str(target))
        recompile(pack_dir, target)
        done.append(f"{pack_dir.relative_to(rules_dir)} <- _inbox/{document.name}")

    if packs_dir.is_dir():
        for pack_dir in sorted(path for path in packs_dir.iterdir() if path.is_dir()):
            documents = source_documents(pack_dir)
            if not documents:
                continue
            newest = max(documents, key=lambda path: path.stat().st_mtime)
            if not is_stale(pack_dir, newest):
                continue
            if args.check:
                pending.append(f"{pack_dir.relative_to(rules_dir)} (pack.json 缺失或过期)")
                continue
            recompile(pack_dir, newest)
            done.append(str(pack_dir.relative_to(rules_dir)))

    for item in done:
        print(f"[OK] compiled {item}")
    for item in pending:
        print(f"[PENDING] {item}")

    if pending:
        if args.check:
            print()
            print("规则文档尚未转成规则包；先运行 rules_sync.py，再做审核。")
        return 1
    if not done and not pending:
        print("[OK] 所有规则文档都已编译，无需同步")
    else:
        print()
        print("规则包已更新为 draft；校验后运行 rules_validate.py <pack.json> --activate 启用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
