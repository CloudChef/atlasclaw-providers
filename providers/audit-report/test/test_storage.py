from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API))
from storage import report_data_dir, shared_data_dir  # noqa: E402


def test_configured_roots_are_isolated_by_tenant_and_user(tmp_path):
    root = tmp_path / "reports"
    host = SimpleNamespace(
        data_dir=tmp_path / "index",
        shared_data_dir=tmp_path / "shared",
        user=SimpleNamespace(tenant_id="tenant-a", user_id="alice"),
        config={"reports_dir": str(root), "standards_dir": str(tmp_path / "standards")},
    )
    assert report_data_dir(host) == root / "tenant-a" / "alice"
    assert shared_data_dir(host) == tmp_path / "standards"


def test_default_roots_preserve_host_layout(tmp_path):
    host = SimpleNamespace(data_dir=tmp_path / "user", shared_data_dir=tmp_path / "shared")
    assert report_data_dir(host) == tmp_path / "user"
    assert shared_data_dir(host) == tmp_path / "shared"


def test_configured_root_requires_absolute_path(tmp_path):
    value = "relative/path"
    host = SimpleNamespace(data_dir=tmp_path, user=SimpleNamespace(tenant_id="t", user_id="u"), config={"reports_dir": value})
    with pytest.raises(ValueError):
        report_data_dir(host)


def test_blank_configured_root_preserves_legacy_path(tmp_path):
    host = SimpleNamespace(data_dir=tmp_path / "user", config={"reports_dir": " "})
    assert report_data_dir(host) == tmp_path / "user"


def test_user_and_tenant_segments_reject_traversal(tmp_path):
    host = SimpleNamespace(data_dir=tmp_path, config={"reports_dir": str(tmp_path / "reports")},
                           user=SimpleNamespace(tenant_id="../other", user_id="alice"))
    with pytest.raises(ValueError):
        report_data_dir(host)


def test_get_config_is_used_when_available(tmp_path):
    class Host:
        data_dir = tmp_path / "index"
        user = SimpleNamespace(tenant_id="tenant", user_id="bob")

        def get_config(self, key, default=None):
            return {"reports_dir": str(tmp_path / "reports")}.get(key, default)

    assert report_data_dir(Host()) == tmp_path / "reports" / "tenant" / "bob"
