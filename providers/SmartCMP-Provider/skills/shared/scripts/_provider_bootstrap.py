"""Load the co-located SmartCMP Provider for AtlasClaw Skill handlers."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

_PROVIDER_ROOT = Path(__file__).resolve().parents[3]
_PROVIDER_SRC = _PROVIDER_ROOT / "src"


def _is_colocated_module(module: ModuleType) -> bool:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    return Path(module_file).resolve().is_relative_to(_PROVIDER_SRC)


def _foreign_provider_modules() -> dict[str, str]:
    foreign_modules: dict[str, str] = {}
    for module_name, module in sys.modules.items():
        if module_name != "smartcmp_provider" and not module_name.startswith(
            "smartcmp_provider."
        ):
            continue
        if not isinstance(module, ModuleType) or not _is_colocated_module(module):
            foreign_modules[module_name] = str(getattr(module, "__file__", "<unknown>"))
    return foreign_modules


def provider_src() -> Path:
    """Return the co-located SmartCMP Provider source directory.

    Returns:
        Absolute ``src`` directory owned by this SmartCMP Provider checkout.
    """

    return _PROVIDER_SRC


def ensure_provider_importable() -> Path:
    """Prepend the co-located SmartCMP Provider source path for this handler process.

    This compatibility hook changes only the current Python process import path.
    It does not read Provider configuration, resolve credentials, or belong in
    the long-running MCP process.

    Returns:
        Absolute source directory inserted into ``sys.path``.

    Raises:
        RuntimeError: If the deployed Provider does not contain the expected
            ``smartcmp_provider`` package.
    """

    package_dir = _PROVIDER_SRC / "smartcmp_provider"
    if not package_dir.is_dir():
        raise RuntimeError(f"SmartCMP Provider package is missing: {package_dir}")

    source_path = str(_PROVIDER_SRC)
    sys.path[:] = [entry for entry in sys.path if entry != source_path]
    sys.path.insert(0, source_path)
    return _PROVIDER_SRC


def load_provider() -> ModuleType:
    """Import and return the co-located ``smartcmp_provider`` package.

    Returns:
        Imported SmartCMP Provider module from this Provider checkout.

    Raises:
        RuntimeError: If the co-located package is missing, another SmartCMP Provider
            is already imported, or Python resolves the wrong package.
        ModuleNotFoundError: If Python cannot import the package after bootstrap.
    """

    ensure_provider_importable()
    foreign_modules = _foreign_provider_modules()
    if foreign_modules:
        origins = ", ".join(
            f"{name}={origin}" for name, origin in sorted(foreign_modules.items())
        )
        raise RuntimeError(
            "Refusing to reuse a non-colocated SmartCMP Provider module: "
            f"{origins}"
        )

    provider = importlib.import_module("smartcmp_provider")
    if not _is_colocated_module(provider):
        raise RuntimeError(
            "SmartCMP Provider resolved outside the deployed Provider: "
            f"{getattr(provider, '__file__', '<unknown>')}"
        )
    return provider
