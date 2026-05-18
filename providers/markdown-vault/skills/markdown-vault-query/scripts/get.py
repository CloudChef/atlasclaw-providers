"""Runtime read entry point for the Markdown Vault provider."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from _config import MarkdownVaultConfigError, load_provider_config_from_env
from _parser import VaultPathError, read_markdown_lines


def main(argv: list[str] | None = None) -> int:
    """Run `markdown_vault_get` as a CLI-compatible AtlasClaw skill script."""

    parser = argparse.ArgumentParser(description="Read a bounded Markdown vault line range.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--start-line", type=int, default=None)
    parser.add_argument("--end-line", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        config = load_provider_config_from_env()
        payload = read_markdown_lines(
            config,
            args.path,
            start_line=args.start_line,
            end_line=args.end_line,
        )
        payload.update({"success": True})
        _emit(payload)
        return 0
    except (MarkdownVaultConfigError, VaultPathError) as exc:
        _emit_error("read_failed", str(exc))
        return 0
    except Exception as exc:  # Runtime boundary: return a structured tool error instead of raw traceback.
        _emit_error("read_failed", str(exc))
        return 0


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
