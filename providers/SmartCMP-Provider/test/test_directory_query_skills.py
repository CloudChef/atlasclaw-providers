import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parents[3]
PROVIDER_ROOT = REPO_ROOT / "providers" / "SmartCMP-Provider"


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _unexpected_http_call(*args, **kwargs):
    raise AssertionError("Unexpected HTTP call in test.")


def run_script(monkeypatch, relative_script_path: str, argv: list[str], *, fake_get=None):
    script_path = PROVIDER_ROOT / relative_script_path
    module_name = f"test_{script_path.stem}_module"

    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=test-token")
    monkeypatch.setattr(requests, "get", fake_get or _unexpected_http_call)
    monkeypatch.setattr(sys, "argv", [script_path.name, *argv])

    stdout = io.StringIO()
    stderr = io.StringIO()
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    return stdout.getvalue(), stderr.getvalue()


def extract_meta(stderr: str, block_name: str):
    match = re.search(
        rf"##{block_name}_START##\s*(.*?)\s*##{block_name}_END##",
        stderr,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_list_all_business_groups_hits_ui_directory_endpoint(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse(
            {
                "content": [
                    {"id": "bg-1", "name": "业务组A", "code": "BG-A"},
                    {"id": "bg-2", "nameZh": "业务组B", "code": "BG-B"},
                ]
            }
        )

    stdout, stderr = run_script(
        monkeypatch,
        "skills/business-group/scripts/list_all_business_groups.py",
        [],
        fake_get=fake_get,
    )
    payload = extract_meta(stderr, "BUSINESS_GROUP_DIRECTORY_META")

    assert captured["url"] == (
        "https://cmp.example.com/platform-api/business-groups/has-update-permission"
        "?query&sort=updatedDate%2Cdesc&page=1&size=65535&queryValue="
    )
    assert "Found 2 business group(s):" in stdout
    assert "业务组A" in stdout
    assert "业务组B" in stdout
    assert "请选择" not in stdout
    assert payload[0] == {
        "index": 1,
        "id": "bg-1",
        "name": "业务组A",
        "code": "BG-A",
    }
    assert payload[1]["id"] == "bg-2"
    assert payload[1]["name"] == "业务组B"


def test_list_all_resource_pools_supports_keyword_filter(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "rb-1",
                        "name": "生产资源池",
                        "businessGroupId": "bg-prod",
                        "cloudEntryTypeId": "yacmp:cloudentry:type:vsphere",
                    }
                ]
            }
        )

    stdout, stderr = run_script(
        monkeypatch,
        "skills/resource-pool/scripts/list_all_resource_pools.py",
        ["生产"],
        fake_get=fake_get,
    )
    payload = extract_meta(stderr, "RESOURCE_POOL_DIRECTORY_META")

    assert captured["url"] == (
        "https://cmp.example.com/platform-api/resource-bundles"
        "?query&sort=createdDate%2Cdesc&page=1&size=65535&queryValue=%E7%94%9F%E4%BA%A7"
    )
    assert "Found 1 resource pool(s):" in stdout
    assert "生产资源池" in stdout
    assert "请选择" not in stdout
    assert payload[0] == {
        "index": 1,
        "id": "rb-1",
        "name": "生产资源池",
        "businessGroupId": "bg-prod",
        "cloudEntryTypeId": "yacmp:cloudentry:type:vsphere",
    }
