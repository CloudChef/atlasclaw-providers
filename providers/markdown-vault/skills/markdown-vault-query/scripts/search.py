"""Runtime search entry point for the Markdown Vault provider."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from _config import MarkdownVaultConfigError, load_provider_config_from_env
from _index import open_index_store
from _parser import collect_current_file_state


def main(argv: list[str] | None = None) -> int:
    """Run `markdown_vault_search` as a CLI-compatible AtlasClaw skill script."""

    parser = argparse.ArgumentParser(description="Search an indexed Markdown vault.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--path-filter", default="")
    parser.add_argument("--tag-filter", default="")
    args = parser.parse_args(argv)

    try:
        config = load_provider_config_from_env()
        store = open_index_store(config)
        current_state = collect_current_file_state(config)
        payload = store.search(
            args.query,
            limit=max(1, min(args.limit, 20)),
            path_filter=args.path_filter or None,
            tag_filter=args.tag_filter or None,
            current_state=current_state,
        )
        _emit(payload)
        return 0
    except MarkdownVaultConfigError as exc:
        _emit_error("configuration_error", str(exc))
        return 0
    except Exception as exc:  # Runtime boundary: return a structured tool error instead of raw traceback.
        _emit_error("search_failed", str(exc))
        return 0


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
