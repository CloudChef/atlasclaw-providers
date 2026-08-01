#!/usr/bin/env python3
"""Run the no-network SmartCMP Provider migration preflight.

The historical filename is retained for local compatibility, but live SmartCMP
E2E now runs through AtlasClaw and the standalone MCP service as documented in
``local-docs/test-plan/e2e-test-plan.md``. This command validates the current
grouped Skill adapters and Provider contracts; it never invokes deleted
one-command scripts or contacts CMP.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
CRITICAL_TARGETS = (
    "test/test_atlasclaw_skill_compatibility.py",
    "test/test_skill_adapters.py",
)


def build_command(*, full: bool = False) -> list[str]:
    """Build the pytest command for critical preflight or the full unit gate."""

    targets = ("test",) if full else CRITICAL_TARGETS
    return [sys.executable, "-m", "pytest", "-q", *targets]


def main(argv: list[str] | None = None) -> int:
    """Execute the selected local gate and return pytest's exit status."""

    parser = argparse.ArgumentParser(
        description="Run SmartCMP Provider no-network migration checks."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the complete Provider unit suite instead of critical preflight.",
    )
    args = parser.parse_args(argv)
    result = subprocess.run(
        build_command(full=args.full),
        cwd=PROVIDER_ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
