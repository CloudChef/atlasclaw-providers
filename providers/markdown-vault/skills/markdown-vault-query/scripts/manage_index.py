"""Offline admin script for refreshing and inspecting Markdown Vault indexes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from _config import MarkdownVaultConfigError, PROVIDER_TYPE, load_provider_config_from_file
from _index import open_index_store
from _parser import collect_current_file_state, parse_vault


def main(argv: list[str] | None = None) -> int:
    """Run the offline `refresh` or `status` admin command for one provider instance."""

    parser = argparse.ArgumentParser(description="Manage a Markdown vault provider index.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("refresh", "status"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--config", required=True, type=Path)
        command_parser.add_argument("--instance", required=True)
        command_parser.add_argument("--provider-type", default=PROVIDER_TYPE)
    args = parser.parse_args(argv)

    try:
        config = load_provider_config_from_file(
            args.config,
            instance_name=args.instance,
            provider_type=args.provider_type,
        )
        store = open_index_store(config)
        if args.command == "refresh":
            payload = _refresh(config, store)
        else:
            payload = _status(config, store)
        _emit(payload)
        return 0
    except MarkdownVaultConfigError as exc:
        _emit_error("configuration_error", str(exc))
        return 2
    except Exception as exc:
        _emit_error("index_management_failed", str(exc))
        return 1


def _refresh(config: Any, store: Any) -> dict[str, Any]:
    documents = parse_vault(config)
    store.replace_index(documents)
    current_state = collect_current_file_state(config)
    status = store.status(current_state)
    return {
        "success": True,
        "action": "refresh",
        "provider_instance": config.instance_name,
        "indexed_documents": len(documents),
        "indexed_chunks": sum(len(document.chunks) for document in documents),
        "status": _status_payload(status),
    }


def _status(config: Any, store: Any) -> dict[str, Any]:
    current_state = collect_current_file_state(config)
    status = store.status(current_state)
    return {
        "success": True,
        "action": "status",
        "provider_instance": config.instance_name,
        "status": _status_payload(status),
    }


def _status_payload(status: Any) -> dict[str, Any]:
    return {
        "index_built": status.index_built,
        "stale": status.stale,
        "indexed_documents": status.indexed_documents,
        "indexed_chunks": status.indexed_chunks,
        "current_documents": status.current_documents,
        "changed_paths": status.changed_paths,
        "deleted_paths": status.deleted_paths,
    }


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _emit_error(error_code: str, message: str) -> None:
    _emit(
        {
            "success": False,
            "error_code": error_code,
            "error": message,
        }
    )


if __name__ == "__main__":
    sys.exit(main())
