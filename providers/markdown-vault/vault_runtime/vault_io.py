"""Filesystem contracts and transaction recovery shared by Markdown Vault runtimes."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
from typing import Iterator


TRANSACTION_DIR_NAME = ".atlasclaw-transactions"
UNPUBLISHED_DIR_NAME = ".atlasclaw-unpublished"
INTERNAL_PROVIDER_DIRS = frozenset({TRANSACTION_DIR_NAME, UNPUBLISHED_DIR_NAME})
_TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TRANSACTION_PHASES = {"PREPARED", "OLD_MOVED", "NEW_INSTALLED", "COMMITTED"}


class VaultTransactionError(RuntimeError):
    """Raised when an interrupted transaction cannot be recovered without data loss."""


def recover_vault_transactions(vault_path: Path) -> None:
    """Recover marker-validated swaps and discard transactions that never entered exchange."""
    vault_root = vault_path.resolve()
    transaction_root = vault_root / TRANSACTION_DIR_NAME
    if not transaction_root.exists():
        return
    if transaction_root.is_symlink() or not transaction_root.is_dir():
        raise VaultTransactionError("Knowledge transaction root is unsafe")
    for transaction in transaction_root.iterdir():
        if (
            not transaction.is_dir()
            or transaction.is_symlink()
            or not _TRANSACTION_ID.fullmatch(transaction.name)
        ):
            continue
        marker = _read_transaction_marker(vault_root, transaction)
        previous = transaction / "previous"
        if marker is None:
            if previous.exists() or previous.is_symlink():
                raise VaultTransactionError(
                    "Knowledge transaction has a previous snapshot but no valid marker"
                )
            shutil.rmtree(transaction)
            continue

        target = vault_root / PurePosixPath(marker["targetRelative"])
        target_exists = target.exists() or target.is_symlink()
        previous_exists = previous.exists() or previous.is_symlink()
        phase = marker["phase"]
        if phase == "COMMITTED":
            if not target_exists:
                raise VaultTransactionError("Committed Knowledge transaction lost its new snapshot")
            _validate_transaction_document(vault_root, target, marker, expected="new")
            if previous_exists:
                if not marker["hadTarget"]:
                    raise VaultTransactionError("Create transaction unexpectedly contains a previous snapshot")
                _validate_transaction_document(vault_root, previous, marker, expected="previous")
            _remove_transaction(transaction)
            continue

        if previous_exists:
            if not marker["hadTarget"]:
                raise VaultTransactionError("Create transaction unexpectedly contains a previous snapshot")
            if not previous.is_dir() or previous.is_symlink():
                raise VaultTransactionError("Knowledge transaction previous snapshot is unsafe")
            _validate_transaction_document(vault_root, previous, marker, expected="previous")
            if target_exists:
                _validate_transaction_document(vault_root, target, marker, expected="new")
                shutil.rmtree(target)
                fsync_directory(target.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(previous, target)
            fsync_directory(transaction)
            fsync_directory(target.parent)
            _remove_transaction(transaction)
            continue

        if marker["hadTarget"]:
            if target_exists:
                try:
                    _validate_transaction_document(
                        vault_root,
                        target,
                        marker,
                        expected="previous",
                    )
                except VaultTransactionError:
                    if phase != "PREPARED":
                        raise VaultTransactionError(
                            "Knowledge transaction lost its previous snapshot"
                        )
                else:
                    _remove_transaction(transaction)
                    continue
            if phase == "PREPARED":
                _remove_transaction(transaction)
                continue
            raise VaultTransactionError("Knowledge transaction lost its previous snapshot")

        if target_exists and phase != "PREPARED":
            _validate_transaction_document(vault_root, target, marker, expected="new")
            shutil.rmtree(target)
            fsync_directory(target.parent)
        _remove_transaction(transaction)


def _read_transaction_marker(vault_path: Path, transaction: Path) -> dict | None:
    """Return a validated marker, or None when exchange never started and cleanup is safe."""
    marker_path = transaction / "transaction.json"
    previous = transaction / "previous"
    if marker_path.is_symlink():
        raise VaultTransactionError("Knowledge transaction marker is unsafe")
    try:
        if marker_path.stat().st_size > 64 * 1024:
            raise VaultTransactionError("Knowledge transaction marker is too large")
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        if previous.exists() or previous.is_symlink():
            raise VaultTransactionError(
                "Knowledge transaction has a previous snapshot but no valid marker"
            )
        return None
    except OSError as exc:
        raise VaultTransactionError("Knowledge transaction marker is unreadable") from exc
    if not isinstance(marker, dict) or marker.get("transactionId") != transaction.name:
        raise VaultTransactionError("Knowledge transaction marker is invalid")
    try:
        knowledge_id = normalize_identifier(marker.get("knowledgeId"), "knowledgeId")
        target_path = normalize_target_path(marker.get("targetPath"))
    except ValueError as exc:
        raise VaultTransactionError("Knowledge transaction target is invalid") from exc
    expected_relative = f"{target_path}/{knowledge_id}" if target_path else knowledge_id
    if marker.get("targetRelative") != expected_relative or not isinstance(marker.get("hadTarget"), bool):
        raise VaultTransactionError("Knowledge transaction target is invalid")
    phase = str(marker.get("phase") or "")
    new_fingerprint = str(marker.get("newSourceFingerprint") or "")
    previous_state = marker.get("previousState")
    if phase not in _TRANSACTION_PHASES or not new_fingerprint:
        raise VaultTransactionError("Knowledge transaction phase or new version is invalid")
    if marker["hadTarget"]:
        if (
            not isinstance(previous_state, dict)
            or not isinstance(previous_state.get("inode"), int)
            or previous_state["inode"] <= 0
            or not _SHA256.fullmatch(str(previous_state.get("manifestSha256") or ""))
        ):
            raise VaultTransactionError("Knowledge transaction previous version is invalid")
    elif previous_state is not None:
        raise VaultTransactionError("Create transaction cannot declare a previous version")
    target = (vault_path / PurePosixPath(expected_relative)).resolve()
    if vault_path not in target.parents or contains_symlink(vault_path, target.parent):
        raise VaultTransactionError("Knowledge transaction target is unsafe")
    marker["knowledgeId"] = knowledge_id
    marker["targetPath"] = target_path
    marker["phase"] = phase
    marker["newSourceFingerprint"] = new_fingerprint
    return marker


def _validate_transaction_document(
    vault_path: Path,
    document_root: Path,
    marker: dict,
    *,
    expected: str,
) -> None:
    """Match a recovery candidate to the provider-owned identity in its journal."""
    manifest_path = document_root / "manifest.json"
    if document_root.is_symlink() or manifest_path.is_symlink():
        raise VaultTransactionError("Knowledge transaction snapshot uses a symlink")
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VaultTransactionError("Knowledge transaction snapshot is unreadable") from exc
    if not isinstance(manifest, dict) or (
        str(manifest.get("providerType") or "") != "markdown-vault"
        or str(manifest.get("sourceSystem") or "").strip().lower() != "smartcmp"
        or str(manifest.get("knowledgeId") or "") != marker["knowledgeId"]
        or str(manifest.get("targetPath") or "") != marker["targetPath"]
    ):
        raise VaultTransactionError("Knowledge transaction snapshot does not match its marker")
    final_path = vault_path / PurePosixPath(marker["targetRelative"])
    previous_path = vault_path / TRANSACTION_DIR_NAME / marker["transactionId"] / "previous"
    if document_root not in {final_path, previous_path}:
        raise VaultTransactionError("Knowledge transaction snapshot path is invalid")
    if expected == "previous":
        state = marker["previousState"]
        if (
            document_root.stat().st_ino != state["inode"]
            or hashlib.sha256(manifest_bytes).hexdigest() != state["manifestSha256"]
        ):
            raise VaultTransactionError("Knowledge previous snapshot changed after transaction start")
    elif expected == "new":
        if str(manifest.get("sourceFingerprint") or "") != marker["newSourceFingerprint"]:
            raise VaultTransactionError("Knowledge new snapshot does not match its transaction")
    else:
        raise VaultTransactionError("Knowledge transaction validation mode is invalid")


def _remove_transaction(transaction: Path) -> None:
    """Remove recovered transaction state and persist the parent directory update."""
    parent = transaction.parent
    shutil.rmtree(transaction)
    fsync_directory(parent)


def normalize_identifier(value: object, name: str) -> str:
    """Normalize an external Knowledge identifier.

    Args:
        value: Raw identifier supplied by REST input or a transaction marker.
        name: Field name used in validation errors.

    Returns:
        The trimmed safe identifier.

    Raises:
        ValueError: If the identifier cannot be represented by one safe path segment.
    """
    normalized = str(value or "").strip()
    if not _SAFE_IDENTIFIER.fullmatch(normalized) or normalized in {".", ".."}:
        raise ValueError(f"Invalid {name}")
    return normalized


def normalize_target_path(value: object) -> str:
    """Normalize a safe optional Vault-relative target directory.

    Args:
        value: Raw target path supplied by REST input or a transaction marker.

    Returns:
        A normalized POSIX-style relative path, or an empty string for the Vault root.

    Raises:
        ValueError: If the path is absolute, hidden, empty-segmented, or traversing.
    """
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    if "\\" in raw_value or "\x00" in raw_value or raw_value.startswith("/"):
        raise ValueError("Invalid targetPath")
    parts = raw_value.split("/")
    if any(part in {"", ".", ".."} or part.startswith(".") for part in parts):
        raise ValueError("targetPath must stay inside the Vault")
    return "/".join(parts)


def contains_symlink(vault_path: Path, candidate: Path) -> bool:
    """Return whether a candidate escapes the Vault or traverses a symlink.

    Args:
        vault_path: Trusted Vault root.
        candidate: Path whose components must remain below the Vault without symlinks.

    Returns:
        ``True`` when the candidate is outside the Vault or contains a symlink.
    """
    try:
        relative = candidate.absolute().relative_to(vault_path.absolute())
    except ValueError:
        return True
    current = vault_path
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def fsync_directory(path: Path) -> None:
    """Persist directory entry changes needed by Knowledge filesystem transactions.

    Args:
        path: Existing directory whose metadata must be flushed.

    Raises:
        OSError: If the directory cannot be opened or synchronized.
    """
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def vault_read_lock(vault_path: Path) -> Iterator[None]:
    """Keep concurrent reads shared, escalating only when transaction recovery is pending."""
    descriptor = os.open(
        vault_path / ".atlasclaw-knowledge.lock",
        os.O_CREAT | os.O_RDWR,
        0o600,
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        if _has_pending_transactions(vault_path):
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            recover_vault_transactions(vault_path)
            fcntl.flock(descriptor, fcntl.LOCK_SH)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _has_pending_transactions(vault_path: Path) -> bool:
    """Check for provider-owned UUID transaction directories while holding a shared lock."""
    transaction_root = vault_path / TRANSACTION_DIR_NAME
    if not transaction_root.exists():
        return False
    if transaction_root.is_symlink() or not transaction_root.is_dir():
        return True
    return any(
        candidate.is_dir()
        and not candidate.is_symlink()
        and bool(_TRANSACTION_ID.fullmatch(candidate.name))
        for candidate in transaction_root.iterdir()
    )
