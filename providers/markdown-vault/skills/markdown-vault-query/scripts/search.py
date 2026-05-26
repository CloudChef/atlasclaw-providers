"""Runtime search entry point for the Markdown Vault provider."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from _config import MarkdownVaultConfigError, load_provider_config_from_env
from _direct_search import search_direct
from _parser import iter_markdown_files


def main(argv: list[str] | None = None) -> int:
    """Run `markdown_vault_search` as a CLI-compatible AtlasClaw skill script."""

    parser = argparse.ArgumentParser(description="Search a Markdown vault directly.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--keywords", nargs="*", default=[])
    parser.add_argument("--keywords-json", default="[]")
    parser.add_argument("--keyword", action="append", default=[])
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--path-filter", default="")
    parser.add_argument("--tag-filter", default="")
    args = parser.parse_args(argv)

    try:
        config = load_provider_config_from_env()
        payload = search_direct(
            config,
            args.query,
            keywords=[*args.keywords, *args.keyword, *_keywords_from_json(args.keywords_json)],
            limit=max(1, min(args.limit, 50)),
            path_filter=_runtime_path_filter(args.path_filter, config) or None,
            tag_filter=args.tag_filter or None,
        )
        _emit(payload)
        return 0
    except MarkdownVaultConfigError as exc:
        _emit_error("configuration_error", str(exc))
        return 0
    except Exception as exc:  # Runtime boundary: return a structured tool error instead of raw traceback.
        _emit_error("search_failed", str(exc))
        return 0


def _keywords_from_json(value: str) -> list[str]:
    if not value or not value.strip():
        return []
    payload = json.loads(value)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("--keywords-json must be a JSON array of strings.")
    return [str(item).strip() for item in payload if str(item).strip()]


def _runtime_path_filter(value: str, config: Any) -> str:
    """Keep path filters scoped to vault paths, not provider instance identifiers."""
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    normalized_key = normalized.lower()
    provider_type = str(getattr(config, "provider_type", "") or "").strip().lower()
    instance_name = str(getattr(config, "instance_name", "") or "").strip().lower()
    instance_id = str(getattr(config, "instance_id", "") or "").strip().lower()
    instance_refs = {
        item
        for item in (
            provider_type,
            instance_name,
            instance_id,
            f"{provider_type}.{instance_name}" if provider_type and instance_name else "",
            f"{provider_type}:{instance_name}" if provider_type and instance_name else "",
            _vault_root_name(config),
        )
        if item
    }
    if normalized_key in instance_refs and not _path_filter_matches_vault_path(normalized, config):
        return ""
    return normalized


def _vault_root_name(config: Any) -> str:
    try:
        return str(config.vault_path.name or "").strip().lower()
    except AttributeError:
        return ""


def _path_filter_matches_vault_path(value: str, config: Any) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return False
    try:
        vault_path = config.vault_path
        for file_path in iter_markdown_files(config):
            relative = file_path.relative_to(vault_path).as_posix().lower()
            if normalized in relative:
                return True
    except (AttributeError, OSError, ValueError):
        return False
    return False


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _emit_error(error_code: str, message: str) -> None:
    _emit(
        {
            "success": False,
            "error_code": error_code,
            "error": message,
            "results": [],
        }
    )


if __name__ == "__main__":
    sys.exit(main())
