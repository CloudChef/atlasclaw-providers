"""Runtime search entry point for the Markdown Vault provider."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from _config import MarkdownVaultConfigError, load_provider_config_from_env
from _direct_search import search_direct


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
            path_filter=args.path_filter or None,
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
