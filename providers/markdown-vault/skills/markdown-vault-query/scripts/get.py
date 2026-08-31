"""Runtime read entry point for the Markdown Vault provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROVIDER_ROOT = Path(__file__).resolve().parents[3]
if str(PROVIDER_ROOT) not in sys.path:
    sys.path.insert(0, str(PROVIDER_ROOT))

from vault_runtime.config import MarkdownVaultConfigError, load_provider_config_from_env  # noqa: E402
from vault_runtime.parser import VaultPathError, read_markdown_lines  # noqa: E402
from vault_runtime.vault_io import vault_read_lock  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Run `markdown_vault_get` as a CLI-compatible AtlasClaw skill script."""

    parser = argparse.ArgumentParser(description="Read a bounded Markdown vault line range.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--start-line", type=int, default=None)
    parser.add_argument("--end-line", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        config = load_provider_config_from_env()
        with vault_read_lock(config.vault_path):
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
