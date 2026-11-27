# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Provider-shared audit reference materials and legacy rule-pack operations.

Standards are not per-user: every user who can open the provider sees the same
library. Files live under ``<provider-data-root>/_shared`` instead of the
per-user provider directory::

    _shared/
    |-- standards/<id>/original.<ext>   uploaded reference file
    |-- standards/<id>/standard.json    metadata + read/legacy compile state
    `-- rules/
        |-- config.json                 active packs (absolute or relative paths)
        `-- packs/<slug>/{pack.json,rules.md,source/}

New uploads are read locally as audit reference materials. The explicit legacy
compile operation remains available for records intentionally converted into
rule packs; ordinary uploads never activate rules automatically.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from storage import has_configured_shared_data_dir, shared_data_dir

import batch_audit

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".md", ".txt", ".xlsx", ".xlsm"}
STATUS_COMPILING = "compiling"
STATUS_ACTIVE = "active"
STATUS_FAILED = "failed"
STATUS_UPLOADED = "uploaded"
READ_READING = "reading"
READ_READY = "ready"
READ_FAILED = "failed"
_LIBRARY_LOCK = RLock()


def shared_root(host: Any) -> Path:
    """Return the provider-wide shared directory (not under any user folder)."""
    return shared_data_dir(host)


def standards_root(host: Any) -> Path:
    """Return the shared standards directory."""
    return shared_root(host) / "standards"


def rules_root(host: Any) -> Path:
    """Return the shared rules directory used as ``--rules-dir``."""
    return shared_root(host) / "rules"


def skill_root() -> Path:
    """Return the bundled audit-report skill directory."""
    return Path(__file__).resolve().parents[1] / "skills" / "audit-report"


def _is_builtin_pack(payload: dict[str, Any]) -> bool:
    """Recognize a versioned package-owned built-in rules payload."""
    return payload.get("pack") == "builtin" and isinstance(payload.get("rules"), list) and bool(payload["rules"])


def _version_tuple(value: Any) -> tuple[int, int, int] | None:
    """Parse a numeric semantic version for built-in update comparisons."""
    match = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?\s*", str(value or ""))
    return tuple(int(part) for part in match.groups()) if match else None


def _builtin_subtree_matches(source: Path, target: Path) -> bool:
    """Return whether every shipped file under builtin exists byte-for-byte at target."""
    return all(
        (target / path.relative_to(source)).is_file()
        and (target / path.relative_to(source)).read_bytes() == path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    )


def _refresh_bundled_builtin(source: Path, target: Path) -> None:
    """Refresh only package-owned builtin files while leaving other shared data alone."""
    source_rules = read_json(source / "rules.json")
    if not _is_builtin_pack(source_rules):
        raise ValueError(f"bundled built-in rules are invalid: {source / 'rules.json'}")
    target_rules_path = target / "rules.json"
    if target_rules_path.is_file():
        target_rules = read_json(target_rules_path)
        if not _is_builtin_pack(target_rules):
            return
        target_version = _version_tuple(target_rules.get("version"))
        source_version = _version_tuple(source_rules.get("version"))
        if target_version and source_version and target_version > source_version:
            return
        if _builtin_subtree_matches(source, target):
            return
    shutil.copytree(source, target, dirs_exist_ok=True)


def ensure_rules_config(host: Any) -> Path:
    """Create the shared rules config and store its default builtin with the library."""
    root = rules_root(host)
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "config.json"
    bundled_builtin_dir = skill_root() / "rules" / "builtin"
    bundled_builtin = (bundled_builtin_dir / "rules.json").resolve()
    builtin = root / "builtin" / "rules.json"
    configured_root = has_configured_shared_data_dir(host)
    with _LIBRARY_LOCK:
        config = read_json(config_path) if config_path.is_file() else {}
        configured_builtin = Path(str(config.get("builtin") or "builtin/rules.json"))
        if not configured_builtin.is_absolute():
            configured_builtin = root / configured_builtin
        local_builtin_selected = config_path.is_file() and configured_builtin.resolve() == builtin.resolve()
        if configured_root or builtin.exists() or local_builtin_selected:
            _refresh_bundled_builtin(bundled_builtin_dir, builtin.parent)
        if not config_path.is_file():
            write_json(config_path, {
                "version": 1,
                "builtin": str(builtin.resolve()) if configured_root else str(bundled_builtin),
                "packs": [],
                "allow_overrides": False,
            })
        elif configured_root:
            configured = Path(str(config.get("builtin") or ""))
            if configured.resolve() == bundled_builtin and builtin.is_file():
                config["builtin"] = str(builtin.resolve())
                write_json(config_path, config)
    return config_path


def load_audit_rules(host: Any) -> tuple[list[batch_audit.Rule], list[str]]:
    """Read the active rules as one snapshot of the shared library."""
    with _LIBRARY_LOCK:
        config_path = ensure_rules_config(host)
        return batch_audit.load_rule_set(skill_root(), rules_dir=config_path.parent)


def safe_name(name: str) -> str:
    """Return a filesystem-safe file name that keeps the extension."""
    raw = Path(str(name or "")).name
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).strip(" .") or "standard"
    return stem[:120]


def classify_material(file_name: str) -> str:
    """Classify a shared reference file using the skill's filename rules."""
    scripts = skill_root() / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from audit_materials import classify_material as classify
    return classify(file_name)


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
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


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
    """Persist a shared source record before local reading starts."""
    record = {
        "id": standard_id,
        "file_name": file_name,
        "file_path": str(file_path),
        "extension": extension,
        "size": int(size),
        "sha256": sha256,
        "pages": pages,
        "status": STATUS_UPLOADED,
        "error_message": "",
        "kind": classify_material(file_name),
        "read_status": READ_READING,
        "read_error": "",
        "pack": "",
        "rules": 0,
        "shared": True,
        "uploaded_by": uploader,
        "created_at": _now(),
        "updated_at": _now(),
    }
    with _LIBRARY_LOCK:
        write_json(standard_dir(host, standard_id) / "standard.json", record)
    return record


async def prepare_standard(host: Any, standard_id: str) -> dict[str, Any] | None:
    """Read one shared source file locally and track its independent read state.

    This does not compile or activate rules; legacy compile fields are retained.
    """
    record = get_standard(host, standard_id)
    if record is None:
        return None
    try:
        await asyncio.to_thread(update_standard, host, standard_id, read_status=READ_READING, read_error="",
                                kind=classify_material(str(record.get("file_name") or "")))
    except asyncio.CancelledError:
        await asyncio.shield(asyncio.to_thread(update_standard, host, standard_id,
                                               read_status=READ_FAILED, read_error="读取任务已取消"))
        raise
    source = Path(str(record.get("file_path") or ""))
    try:
        record_dir = standard_dir(host, standard_id)
        try:
            record_dir.resolve().relative_to(standards_root(host).resolve())
        except ValueError as exc:
            raise ValueError("shared record directory escapes the library root") from exc
        source = _contained_file(source, record_dir)
        scripts = skill_root() / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from audit_materials import read_material
        material = await asyncio.to_thread(read_material, source)
        expected = str(record.get("sha256") or "").strip().lower()
        if expected and material["sha256"] != expected:
            raise ValueError("source SHA-256 differs from the uploaded record")
        return await asyncio.to_thread(
            update_standard, host, standard_id,
            kind=classify_material(str(record.get("file_name") or source.name)), read_status=READ_READY,
            read_error="", read_characters=len(material["content"]),
            source_position_count=len(material["source_position"]),
            sha256=material["sha256"],
        )
    except asyncio.CancelledError:
        await asyncio.shield(asyncio.to_thread(update_standard, host, standard_id,
                                               read_status=READ_FAILED, read_error="读取任务已取消"))
        raise
    except Exception as exc:
        # Keep the detail bounded and local; never interpret extraction failure as a business result.
        return await asyncio.to_thread(update_standard, host, standard_id, read_status=READ_FAILED,
                                       read_error=f"{type(exc).__name__}: {exc}"[:500])


def update_standard(host: Any, standard_id: str, **fields: Any) -> dict[str, Any] | None:
    """Update fields on a standard record."""
    with _LIBRARY_LOCK:
        record = get_standard(host, standard_id)
        if record is None:
            return None
        record.update(fields)
        record["updated_at"] = _now()
        write_json(standard_dir(host, standard_id) / "standard.json", record)
        return record


def delete_standard(host: Any, standard_id: str) -> bool:
    """Delete a standard, its compiled pack, and its config entry."""
    with _LIBRARY_LOCK:
        record = get_standard(host, standard_id)
        if record is None:
            return False
        pack_name = str(record.get("pack") or "")
        if pack_name and not _pack_used_by_other_standard(host, standard_id, pack_name):
            deactivate_pack(host, pack_name)
        shutil.rmtree(standard_dir(host, standard_id))
        return True


def _pack_used_by_other_standard(host: Any, standard_id: str, pack_name: str) -> bool:
    # Legacy records can refer to the same filename-derived pack.
    return any(item["id"] != standard_id and item.get("pack") == pack_name for item in list_standards(host))


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
    await asyncio.to_thread(ensure_rules_config, host)
    source = Path(str(record.get("file_path") or ""))
    if not source.is_file():
        await asyncio.to_thread(update_standard, host, standard_id, status=STATUS_FAILED, error_message="原始标准文件已丢失")
        return
    # Build a fresh revision so failed recompiles cannot remove an active pack.
    pack_name = f"standard-{uuid.uuid4().hex}"
    pack_dir = rules_root(host) / "packs" / pack_name
    pack_path = pack_dir / "pack.json"
    await asyncio.to_thread(update_standard, host, standard_id, status=STATUS_COMPILING, error_message="")

    scripts = skill_root() / "scripts"
    compile_cmd = [
        sys.executable, str(scripts / "rules_compile.py"), str(source),
        "--pack", pack_name,
        "--out", str(pack_dir),
        "--title", str(record.get("file_name") or pack_name),
        "--version", "1.0.0",
    ]
    published = False
    try:
        code, output = await _run(compile_cmd, cwd=scripts)
        if code != 0 or not pack_path.is_file():
            await asyncio.to_thread(update_standard, host, standard_id, status=STATUS_FAILED, error_message=_first_error(output) or "未从标准文件中解析出规则")
            return

        validate_cmd = [sys.executable, str(scripts / "rules_validate.py"), str(pack_path)]
        code, output = await _run(validate_cmd, cwd=scripts)
        if code != 0:
            await asyncio.to_thread(update_standard, host, standard_id, status=STATUS_FAILED, error_message=_first_error(output) or "规则包校验未通过")
            return

        publish_task = asyncio.create_task(asyncio.to_thread(
            _publish_compiled_standard, host, standard_id, pack_name, pack_path,
        ))
        try:
            published = await asyncio.shield(publish_task)
        except asyncio.CancelledError:
            published = await publish_task
            raise
    finally:
        if not published:
            if not await asyncio.to_thread(_configured_pack_is_active, host, pack_name):
                shutil.rmtree(pack_dir, ignore_errors=True)


def _publish_compiled_standard(host: Any, standard_id: str, pack_name: str, pack_path: Path) -> bool:
    """Atomically activate a validated pack while holding the shared-library lock."""
    with _LIBRARY_LOCK:
        current = get_standard(host, standard_id)
        if current is None:
            return False
        previous = str(current.get("pack") or "")
        drop_previous = previous and not _pack_used_by_other_standard(host, standard_id, previous)
        config_path = rules_root(host) / "config.json"
        config = read_json(config_path)
        packs = [entry for entry in config.get("packs", []) if not drop_previous or Path(entry).name != previous]
        pack = read_json(pack_path)
        pack["status"] = STATUS_ACTIVE
        write_json(pack_path, pack)
        config["packs"] = [*packs, f"packs/{pack_name}"]
        write_json(config_path, config)
        update_standard(
            host, standard_id, status=STATUS_ACTIVE, error_message="", pack=pack_name,
            rules=len(pack.get("rules") or []), pack_version=str(pack.get("version") or "1.0.0"),
        )
        if drop_previous:
            shutil.rmtree(rules_root(host) / "packs" / previous, ignore_errors=True)
        return True


def _configured_pack_is_active(host: Any, pack_name: str) -> bool:
    """Check whether a failed publisher call committed this pack to shared config."""
    with _LIBRARY_LOCK:
        config = read_json(rules_root(host) / "config.json")
        return any(Path(str(entry)).name == pack_name for entry in config.get("packs", []))


async def _run(cmd: list[str], *, cwd: Path) -> tuple[int, str]:
    """Run a skill script and return its status code and combined output."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        return 1, f"规则编译失败：{exc}"
    try:
        stdout, _ = await proc.communicate()
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        raise
    return int(proc.returncode or 0), stdout.decode("utf-8", "replace")


def _first_error(output: str) -> str:
    """Extract the most useful line from a compiler/validator output."""
    lines = [line.strip() for line in str(output or "").splitlines() if line.strip()]
    for line in lines:
        if line.startswith(("  -", "[FAIL]", "错误", "未从")):
            return line.lstrip("- ").strip()[:400]
    return lines[-1][:400] if lines else ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained_file(path: Path, root: Path) -> Path:
    """Resolve a standard source and reject symlinks or paths outside its ID directory."""
    resolved_root = root.resolve()
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"source path escapes its shared record directory: {path.name}") from exc
    if not resolved.is_file():
        raise ValueError(f"source file is not a regular file: {path.name}")
    return resolved


def _snapshot_rules(host: Any, destination: Path) -> dict[str, Any]:
    """Copy the builtin rule JSON and enabled rule packs into an isolated tree."""
    config_path = ensure_rules_config(host)
    source_root = rules_root(host).resolve()
    config = read_json(config_path)
    builtin_configured = Path(str(config.get("builtin") or "builtin/rules.json"))
    builtin_source = builtin_configured if builtin_configured.is_absolute() else source_root / builtin_configured
    if not builtin_source.is_file():
        raise FileNotFoundError(f"enabled builtin rules are missing: {builtin_source}")
    try:
        builtin_payload = json.loads(builtin_source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"enabled builtin rules are unreadable: {builtin_source.name}") from exc
    if not isinstance(builtin_payload, dict) or not isinstance(builtin_payload.get("rules"), list):
        raise ValueError(f"enabled builtin rules have invalid structure: {builtin_source.name}")

    destination.mkdir(parents=True, exist_ok=True)
    builtin_target = destination / "builtin" / "rules.json"
    builtin_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(builtin_source, builtin_target)
    pack_targets: list[str] = []
    pack_sources: list[dict[str, str]] = []
    used_names: set[str] = set()
    for entry in config.get("packs") or []:
        configured = Path(str(entry))
        source = configured if configured.is_absolute() else source_root / configured
        if source.is_dir():
            pack_dir = source
            pack_file = pack_dir / "pack.json"
        else:
            pack_file = source
            pack_dir = pack_file.parent
        if not pack_file.is_file():
            raise FileNotFoundError(f"enabled rule pack is missing: {entry}")
        try:
            payload = json.loads(pack_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"enabled rule pack is unreadable: {entry}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
            raise ValueError(f"enabled rule pack has invalid structure: {entry}")
        if payload.get("status", "active") != "active":
            # Drafts are intentionally not enabled in a private audit snapshot.
            continue
        pack_name = safe_name(str(payload.get("pack") or pack_dir.name))
        if pack_name in used_names:
            raise ValueError(f"enabled rule packs collide in private snapshot: {pack_name}")
        used_names.add(pack_name)
        target = destination / "packs" / pack_name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"private rule snapshot already exists: {target.name}")
        shutil.copytree(pack_dir, target)
        pack_targets.append(f"packs/{pack_name}")
        pack_sources.append({"pack": pack_name, "sha256": _sha256(target / "pack.json")})

    private_config = {
        "version": int(config.get("version") or 1),
        "builtin": "builtin/rules.json",
        "packs": pack_targets,
        "allow_overrides": bool(config.get("allow_overrides", False)),
    }
    write_json(destination / "config.json", private_config)
    rules, labels = batch_audit.load_rule_set(skill_root(), rules_dir=destination)
    if len(rules) < len(builtin_payload["rules"]) or len(labels) < 1 + len(pack_targets):
        raise ValueError("private rule snapshot did not load every enabled rule source")
    return {
        "rules_dir": str(destination),
        "builtin_sha256": _sha256(builtin_target),
        "packs": pack_sources,
        "rule_ids": [rule.rule_id for rule in rules],
        "labels": labels,
    }


def snapshot_audit_library(host: Any, destination: Path) -> dict[str, Any]:
    """Freeze every shared reference file and enabled rule pack for one audit.

    The shared-library lock is held throughout enumeration, validation, and copy,
    so later uploads/deletions cannot change the returned input set.
    """
    destination = Path(destination).resolve()
    materials_root = destination / "materials"
    private_rules_root = destination / "rules"
    destination.mkdir(parents=True, exist_ok=True)
    materials_root.mkdir(parents=True, exist_ok=True)
    material_paths: list[Path] = []
    materials: list[dict[str, Any]] = []
    manifest_items: list[dict[str, Any]] = []
    with _LIBRARY_LOCK:
        root = standards_root(host)
        records = []
        if root.is_dir():
            for record_dir in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name):
                try:
                    record_dir.resolve().relative_to(root.resolve())
                except ValueError as exc:
                    raise ValueError(f"shared record directory escapes the library root: {record_dir.name}") from exc
                record_path = record_dir / "standard.json"
                if not record_path.is_file():
                    continue  # An interrupted upload without a record is not a published library item.
                try:
                    payload = json.loads(record_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise ValueError(f"shared material record is unreadable: {record_dir.name}/standard.json") from exc
                if not isinstance(payload, dict) or not payload:
                    raise ValueError(f"shared material record has invalid structure: {record_dir.name}/standard.json")
                payload.setdefault("id", record_dir.name)
                if str(payload["id"]) != record_dir.name:
                    raise ValueError(f"shared material record ID does not match its directory: {record_dir.name}")
                records.append(payload)
        records.sort(key=lambda item: str(item.get("id") or ""))
        ids: set[str] = set()
        target_dirs: set[str] = set()
        for index, record in enumerate(records, start=1):
            standard_id = str(record.get("id") or "")
            if not standard_id or standard_id in ids:
                raise ValueError(f"shared library contains an invalid or duplicate record ID: {standard_id!r}")
            ids.add(standard_id)
            record_root = standard_dir(host, standard_id)
            try:
                source_path = _contained_file(Path(str(record.get("file_path") or "")), record_root)
            except (OSError, ValueError) as exc:
                raise ValueError(f"shared material {standard_id} source is unavailable: {exc}") from exc
            source_hash = _sha256(source_path)
            recorded_hash = str(record.get("sha256") or "").strip().lower()
            if recorded_hash and source_hash != recorded_hash:
                raise ValueError(f"shared material {standard_id} hash differs from its record")
            original_name = safe_name(str(record.get("file_name") or source_path.name))
            if Path(original_name).suffix.lower() not in SUPPORTED_SUFFIXES:
                raise ValueError(f"shared material {standard_id} has unsupported type: {Path(original_name).suffix}")
            id_dir_name = safe_name(standard_id)
            if id_dir_name in target_dirs:
                raise ValueError(f"shared record IDs collide in snapshot path: {id_dir_name}")
            target_dirs.add(id_dir_name)
            target_dir = materials_root / id_dir_name
            target_dir.mkdir(parents=True, exist_ok=False)
            target = target_dir / original_name
            shutil.copy2(source_path, target)
            copied_hash = _sha256(target)
            if copied_hash != source_hash:
                raise ValueError(f"shared material {standard_id} changed during snapshot copy")
            scripts = skill_root() / "scripts"
            if str(scripts) not in sys.path:
                sys.path.insert(0, str(scripts))
            from audit_materials import read_material
            extracted = read_material(target, destination / "extract" / id_dir_name)
            if extracted["sha256"] != copied_hash:
                raise ValueError(f"snapshot material {standard_id} hash changed during reading")
            reference_id = f"M{index:02d}"
            material = {
                "reference_id": reference_id,
                "standard_id": standard_id,
                "filename": original_name,
                "kind": extracted["kind"],
                "sha256": copied_hash,
                "content": extracted["content"],
                "source_position": extracted["source_position"],
            }
            material_paths.append(target)
            materials.append(material)
            manifest_items.append({
                "reference_id": reference_id, "standard_id": standard_id,
                "filename": original_name, "kind": extracted["kind"],
                "sha256": copied_hash, "characters": len(extracted["content"]),
                "source_position_count": len(extracted["source_position"]),
            })
        rule_snapshot = _snapshot_rules(host, private_rules_root)
    snapshot = {
        "material_paths": material_paths,
        "materials": materials,
        "rules_dir": Path(rule_snapshot["rules_dir"]),
        "manifest": {"materials": manifest_items, "rules": rule_snapshot},
    }
    write_json(destination / "audit-library-snapshot.json", {
        **snapshot["manifest"],
        "material_paths": [str(path) for path in material_paths],
        "rules_dir": str(snapshot["rules_dir"]),
    })
    return snapshot
