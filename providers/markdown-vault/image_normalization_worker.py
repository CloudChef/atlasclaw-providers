"""Resource-limited BMP normalization worker for Markdown Vault visual input."""

from __future__ import annotations

import math
from pathlib import Path
import resource
import sys

from PIL import Image


def _apply_resource_limits(timeout_seconds: float, max_output_bytes: int) -> None:
    """Limit CPU, address space, and output size before decoding untrusted input."""
    cpu_seconds = max(math.ceil(timeout_seconds), 1)
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    if sys.platform.startswith("linux"):
        memory_bytes = 768 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (max_output_bytes, max_output_bytes))


def main(argv: list[str] | None = None) -> int:
    """Decode one BMP and write bounded PNG output for the visual-model bridge."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 4:
        return 2
    input_path = Path(arguments[0])
    output_path = Path(arguments[1])
    try:
        _apply_resource_limits(float(arguments[2]), int(arguments[3]))
        with Image.open(input_path) as image:
            if image.format != "BMP":
                return 1
            image.load()
            image.convert("RGB").save(output_path, format="PNG")
    except (OSError, ValueError, Image.DecompressionBombError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
