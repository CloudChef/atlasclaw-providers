# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Provider-shared audit standards, compiled into skill rule packs.

Standards are not per-user: every user who can open the provider sees the same
library. Files live under ``<provider-data-root>/_shared`` instead of the
per-user provider directory::

    _shared/
    |-- standards/<id>/original.pdf     uploaded rule document
    |-- standards/<id>/standard.json    metadata + compile state
    `-- rules/
        |-- config.json                 active packs (absolute or relative paths)
        `-- packs/<slug>/{pack.json,rules.md,source/}

Uploading a document compiles it with the skill's own ``rules_compile.py`` and
activates it with ``rules_validate.py --activate``, so the next audit loads it
as a normal rule pack.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_STANDARD_BYTES = 200 * 1024 * 1024
COMPILE_TIMEOUT_SECONDS = 600
SUPPORTED_SUFFIXES = {".pdf", ".docx", ".md", ".txt"}
STATUS_COMPILING = "compiling"
STATUS_ACTIVE = "active"
STATUS_FAILED = "failed"


def shared_root(host: Any) -> Path:
    """Return the provider-wide shared directory (not under any user folder)."""
    data_dir = Path(host.data_dir).resolve()
    provider_root = data_dir.parents[1] if len(data_dir.parents) > 1 else data_dir.parent
    return provider_root / "_shared"


def standards_root(host: Any) -> Path:
    """Return the shared standards directory."""
    return shared_root(host) / "standards"


def rules_root(host: Any) -> Path:
    """Return the shared rules directory used as ``--rules-dir``."""
    return shared_root(host) / "rules"


def skill_root() -> Path:
    """Return the bundled audit-report skill directory."""
    return Path(__file__).resolve().parents[1] / "skills" / "audit-report"


def ensure_rules_config(host: Any) -> Path:
    """Create the shared rules config, pointing builtin at the installed skill."""
    root = rules_root(host)
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "config.json"
    builtin = (skill_root() / "rules" / "builtin" / "rules.json").resolve()
    if not config_path.is_file():
        write_json(config_path, {
            "version": 1,
            "builtin": str(builtin),
            "packs": [],
            "allow_overrides": False,
        })
    return config_path


def safe_name(name: str) -> str:
    """Return a filesystem-safe file name that keeps the extension."""
    raw = Path(str(name or "")).name
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).strip(" .") or "standard"
    return stem[:120]


def slugify(name: str) -> str:
    """Return a rule-pack name (lowercase letters, digits, hyphens)."""
    value = unicodedata.normalize("NFKC", Path(str(name or "")).stem).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    if not value:
        import hashlib

        value = "pack-" + hashlib.sha1(str(name).encode("utf-8")).hexdigest()[:8]
    return value[:60]


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object, returning ``{}`` when missing or invalid."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write an indented UTF-8 JSON document atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def standard_dir(host: Any, standard_id: str) -> Path:
    """Return one standard's directory inside the shared library."""
    return standards_root(host) / str(standard_id)


def get_standard(host: Any, standard_id: str) -> dict[str, Any] | None:
    """Return one standard record, or ``None`` when it does not exist."""
    payload = read_json(standard_dir(host, standard_id) / "standard.json")
    if not payload:
        return None
    payload.setdefault("id", standard_id)
    return payload


def list_standards(host: Any) -> list[dict[str, Any]]:
    """Return every shared standard, newest first."""
    root = standards_root(host)
    if not root.is_dir():
        return []
    items = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        payload = read_json(path / "standard.json")
        if not payload:
            continue
        payload.setdefault("id", path.name)
        items.append(payload)
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items


def create_standard(
    host: Any,
    *,
    standard_id: str,
    file_name: str,
    file_path: Path,
    extension: str,
    size: int,
    sha256: str,
    pages: int | None,
    uploader: str,
) -> dict[str, Any]:
    """Persist a standard record before compilation starts."""
    record = {
        "id": standard_id,
        "file_name": file_name,
        "file_path": str(file_path),
        "extension": extension,
        "size": int(size),
        "sha256": sha256,
        "pages": pages,
        "status": STATUS_COMPILING,
        "error_message": "",
        "pack": "",
        "rules": 0,
        "shared": True,
        "uploaded_by": uploader,
        "created_at": _now(),
        "updated_at": _now(),
    }
    write_json(standard_dir(host, standard_id) / "standard.json", record)
    return record


def update_standard(host: Any, standard_id: str, **fields: Any) -> dict[str, Any] | None:
    """Update fields on a standard record."""
    record = get_standard(host, standard_id)
    if record is None:
        return None
    record.update(fields)
    record["updated_at"] = _now()
    write_json(standard_dir(host, standard_id) / "standard.json", record)
    return record


def delete_standard(host: Any, standard_id: str) -> bool:
    """Delete a standard, its compiled pack, and its config entry."""
    record = get_standard(host, standard_id)
    if record is None:
        return False
    pack_name = str(record.get("pack") or "")
    if pack_name:
        deactivate_pack(host, pack_name)
    shutil.rmtree(standard_dir(host, standard_id), ignore_errors=True)
    return True


def deactivate_pack(host: Any, pack_name: str) -> None:
    """Remove a pack from config.json and delete its directory."""
    config_path = rules_root(host) / "config.json"
    config = read_json(config_path)
    entries = [str(entry) for entry in config.get("packs") or [] if str(entry)]
    kept = [entry for entry in entries if Path(entry).name != pack_name]
    if kept != entries:
        config["packs"] = kept
        write_json(config_path, config)
    pack_dir = rules_root(host) / "packs" / pack_name
    shutil.rmtree(pack_dir, ignore_errors=True)


async def compile_standard(host: Any, standard_id: str) -> None:
    """Compile one uploaded standard into an active rule pack."""
    record = get_standard(host, standard_id)
    if record is None:
        return
    ensure_rules_config(host)
    source = Path(str(record.get("file_path") or ""))
    if not source.is_file():
        update_standard(host, standard_id, status=STATUS_FAILED, error_message="原始标准文件已丢失")
        return
    pack_name = slugify(str(record.get("file_name") or standard_id))
    existing = rules_root(host) / "packs" / pack_name
    if existing.is_dir():
        shutil.rmtree(existing, ignore_errors=True)
    update_standard(host, standard_id, status=STATUS_COMPILING, error_message="", pack="")

    scripts = skill_root() / "scripts"
    compile_cmd = [
        sys.executable, str(scripts / "rules_compile.py"), str(source),
        "--pack", pack_name,
        "--out", str(rules_root(host) / "packs" / pack_name),
        "--title", str(record.get("file_name") or pack_name),
        "--version", "1.0.0",
    ]
    code, output = await _run(compile_cmd, cwd=scripts)
    pack_path = rules_root(host) / "packs" / pack_name / "pack.json"
    if code != 0 or not pack_path.is_file():
        update_standard(
            host, standard_id,
            status=STATUS_FAILED,
            error_message=_first_error(output) or "未从标准文件中解析出规则",
            pack="",
        )
        return

    validate_cmd = [
        sys.executable, str(scripts / "rules_validate.py"), str(pack_path),
        "--rules-dir", str(rules_root(host)), "--activate",
    ]
    code, output = await _run(validate_cmd, cwd=scripts)
    if code != 0:
        update_standard(
            host, standard_id,
            status=STATUS_FAILED,
            error_message=_first_error(output) or "规则包校验未通过",
            pack="",
        )
        return

    pack = read_json(pack_path)
    update_standard(
        host, standard_id,
        status=STATUS_ACTIVE,
        error_message="",
        pack=pack_name,
        rules=len(pack.get("rules") or []),
        pack_version=str(pack.get("version") or "1.0.0"),
    )


async def _run(cmd: list[str], *, cwd: Path) -> tuple[int, str]:
    """Run a skill script and return its status code and combined output."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=COMPILE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return 1, "规则编译超时"
    except OSError as exc:
        return 1, f"规则编译失败：{exc}"
    return int(proc.returncode or 0), stdout.decode("utf-8", "replace")


def _first_error(output: str) -> str:
    """Extract the most useful line from a compiler/validator output."""
    lines = [line.strip() for line in str(output or "").splitlines() if line.strip()]
    for line in lines:
        if line.startswith(("  -", "[FAIL]", "错误", "未从")):
            return line.lstrip("- ").strip()[:400]
    return lines[-1][:400] if lines else ""
