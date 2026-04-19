import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "resource"
    / "scripts"
    / "analyze_resource_detail.py"
)


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def load_module():
    spec = importlib.util.spec_from_file_location("test_resource_detail_analysis_module", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_main_renders_compact_resource_detail(monkeypatch):
    module = load_module()
    captured = {}

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_patch(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        return FakeResponse(
            {
                "id": "res-1",
                "name": "mysqlLinux2",
                "status": "started",
                "hostName": "Compute-9fxzdy",
                "osDescription": "CentOS",
                "imageName": "CentOS 4/5 or newer (64-bit)",
                "sshPort": 22,
                "lastStartedDate": "2026-04-18 23:39:30",
                "externalId": "vm-403",
                "cpus": 1,
                "memory": 1024,
                "diskTotalNum": 1,
                "storage": 50,
                "host": "host-75",
                "deploymentName": "mysqlLinux2",
                "createdDate": "2026-04-18 23:42:05",
                "payType": "PayAsYouGo",
                "leaseType": "Never",
                "retentionAt": "Never",
                "businessGroupName": "team1",
                "ownerName": "platform-admin",
                "cloudEntryType": "vSphere",
                "cloudEntryName": "vsphere",
                "resourceBundleName": "vsphere-pool",
                "vcenterServer": "192.168.1.113",
                "vcenterFolder": "Datacenter1",
                "storagePolicy": "default-storage-policy",
                "ipAddress": "192.168.92.104",
                "physicalHost": "192.168.1.170",
                "physicalManufacturer": "Dell Inc.",
                "physicalModel": "PowerEdge R720",
                "physicalCpuType": "Intel Xeon",
                "physicalCpuUsage": "21.54%",
                "physicalMemoryUsage": "94.39%",
            }
        )

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(requests, "patch", fake_patch)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1"])

    output = stdout.getvalue()

    assert exit_code == 0
    assert captured["url"] == "https://cmp.example.com/platform-api/nodes/res-1/refresh-status"
    assert "mysqlLinux2" in output
    assert "- Status: started" in output
    assert "- Compute: 1 CPU / 1 GB" in output
    assert "Basic Information" in output
    assert "- Operating System: CentOS" in output
    assert "Attributes" in output
    assert "- Cloud Resource ID: vm-403" in output
    assert "Service Information" in output
    assert "Organization Information" in output
    assert "Platform Information" in output
    assert "Disks" in output
    assert "- Disk 1: 50 | CentOS 4/5 or newer (64-bit)" in output
    assert "topLevelKeys" not in output
    assert "sourceEndpoint" not in output


def test_main_prints_response_body_for_request_errors(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_patch(url, headers=None, verify=None, timeout=None):
        raise requests.HTTPError(
            "HTTP 400",
            response=FakeResponse({}, status_code=400, text='{"message":"bad request"}'),
        )

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(requests, "patch", fake_patch)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-2"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "Request failed" in output
    assert '{"message":"bad request"}' in output
