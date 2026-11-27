"""Report runtime dependencies for the audit-report skill.

Run this before the first audit:

    "${ATLASCLAW_PYTHON}" "${ATLASCLAW_SKILL_DIR}/scripts/selfcheck.py"

Exit code 0 means PDF auditing is possible; DOCX desensitization additionally
requires python-docx. Optional tools only affect enhanced evidence collection.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys


def _module_available(*names: str) -> bool:
    """Return whether any importable module name is installed."""
    for name in names:
        try:
            if importlib.util.find_spec(name) is not None:
                return True
        except (ImportError, ValueError):
            continue
    return False


def _binary_available(*names: str) -> str:
    """Return the first resolvable executable name, or an empty string."""
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return ""


def main() -> int:
    """Print a JSON dependency report and return a readiness exit code."""
    payload = {
        "python": sys.version.split()[0],
        "pymupdf": _module_available("pymupdf", "fitz"),
        "python_docx": _module_available("docx"),
        "openpyxl": _module_available("openpyxl"),
        "httpx": _module_available("httpx"),
        "dotenv": _module_available("dotenv"),
        "win32com": _module_available("win32com"),
        "libreoffice": _binary_available("soffice", "libreoffice"),
        "skill_dir": str(__file__),
    }
    payload["ready"] = payload["pymupdf"]
    payload["full_ready"] = payload["pymupdf"] and payload["python_docx"]
    payload["visual_ready"] = payload["pymupdf"] and payload["httpx"] and (
        bool(payload["libreoffice"]) or payload["win32com"]
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["pymupdf"]:
        print("Missing PyMuPDF: pip install pymupdf", file=sys.stderr)
    if not payload["python_docx"]:
        print("Missing python-docx: pip install python-docx", file=sys.stderr)
    if not payload["openpyxl"]:
        print("Missing openpyxl: pip install openpyxl (Excel rules/materials)", file=sys.stderr)
    if not payload["visual_ready"]:
        print("Visual review needs httpx plus LibreOffice or Windows Word (pywin32)", file=sys.stderr)
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
