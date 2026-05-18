from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from handler import create_deck_handler  # noqa: E402


def test_create_deck_handler_returns_absolute_artifact_path_inside_work_dir(tmp_path: Path) -> None:
    """Verify the PPTX artifact contract used by AtlasClaw download collection."""

    work_dir = tmp_path / "users" / "admin" / "work_dir"
    ctx = SimpleNamespace(deps=SimpleNamespace(extra={"work_dir": str(work_dir)}))

    result = create_deck_handler(
        ctx,
        items=[{"title": "Approval request", "approver": "alice"}],
        title="Approvals",
        output_filename="approvals.pptx",
    )

    artifact_path = Path(result["artifact_path"])
    assert result["success"] is True
    assert artifact_path.is_absolute()
    assert artifact_path.is_file()
    assert artifact_path.resolve().relative_to(work_dir.resolve())
    assert result["file_path"] == result["artifact_path"]
