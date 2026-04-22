import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "shared"
    / "scripts"
)

DATASOURCE_SCRIPTS_DIR = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "datasource"
    / "scripts"
)


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


def run_script(monkeypatch, script_name: str, argv: list[str], *, fake_get=None, fake_post=None, scripts_dir=None):
    script_path = (scripts_dir or SCRIPTS_DIR) / script_name
    module_name = f"test_{script_path.stem}_module"

    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=test-token")
    monkeypatch.setattr(requests, "get", fake_get or _unexpected_http_call)
    monkeypatch.setattr(requests, "post", fake_post or _unexpected_http_call)
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


def test_list_services_preserves_instruction_fields(monkeypatch):
    instructions = {
        "parameters": [
            {
                "key": "name",
                "label": "Resource Name",
                "required": True,
                "source": None,
                "defaultValue": None,
            },
            {
                "key": "businessGroupId",
                "label": "Business Group",
                "required": True,
                "source": "list:business_groups",
                "defaultValue": None,
            },
            {
                "key": "cpu",
                "label": "CPU",
                "required": False,
                "source": None,
                "defaultValue": 2,
            },
        ]
    }

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/published"
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "catalog-1",
                        "nameZh": "Linux VM",
                        "sourceKey": "resource.iaas.machine.instance.abstract",
                        "serviceCategory": "VM",
                        "instructions": json.dumps(instructions, ensure_ascii=False),
                    }
                ],
                "totalElements": 1,
            }
        )

    stdout, stderr = run_script(monkeypatch, "list_services.py", [], fake_get=fake_get, scripts_dir=DATASOURCE_SCRIPTS_DIR)
    payload = extract_meta(stderr, "CATALOG_META")
    catalogs = payload["catalogs"]

    assert "Found 1 published catalog(s)." in stdout
    assert catalogs[0]["instructions"]["parameters"][0]["defaultValue"] is None
    assert catalogs[0]["params"][0]["source"] is None
    assert catalogs[0]["params"][0]["required"] is True
    assert catalogs[0]["params"][1]["source"] == "list:business_groups"
    assert catalogs[0]["params"][2]["defaultValue"] == 2


def test_list_services_marks_explicit_runtime_defaults_as_non_serializable(monkeypatch):
    instructions = {
        "parameters": [
            {
                "key": "resourceBundleName",
                "label": "Resource Pool",
                "required": False,
                "source": None,
                "defaultValue": "vsphere资源池",
                "runtimeDefaultOnly": True,
            },
            {
                "key": "computeProfileName",
                "label": "Compute Profile",
                "required": False,
                "source": None,
                "defaultValue": "微型计算",
                "metadata": {"runtimeDefaultOnly": True},
            },
            {
                "key": "networkId",
                "label": "Network",
                "required": True,
                "source": None,
                "defaultValue": "network-78",
            },
        ]
    }

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/published"
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "catalog-1",
                        "nameZh": "Linux VM",
                        "sourceKey": "resource.iaas.machine.instance.abstract",
                        "serviceCategory": "VM",
                        "instructions": json.dumps(instructions, ensure_ascii=False),
                    }
                ],
                "totalElements": 1,
            }
        )

    _, stderr = run_script(monkeypatch, "list_services.py", [], fake_get=fake_get, scripts_dir=DATASOURCE_SCRIPTS_DIR)
    payload = extract_meta(stderr, "CATALOG_META")
    params = payload["catalogs"][0]["params"]

    assert params[0]["defaultValue"] is None
    assert params[0]["runtimeDefaultOnly"] is True
    assert params[1]["defaultValue"] is None
    assert params[1]["runtimeDefaultOnly"] is True
    assert params[2]["defaultValue"] == "network-78"
    assert "runtimeDefaultOnly" not in params[2]


def test_list_services_keeps_plain_defaults_when_runtime_only_flag_is_absent(monkeypatch):
    instructions = {
        "parameters": [
            {
                "key": "templateId",
                "label": "Template",
                "required": False,
                "source": None,
                "defaultValue": "vm-531",
            }
        ]
    }

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/published"
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "catalog-1",
                        "nameZh": "Linux VM",
                        "sourceKey": "resource.iaas.machine.instance.abstract",
                        "serviceCategory": "VM",
                        "instructions": json.dumps(instructions, ensure_ascii=False),
                    }
                ],
                "totalElements": 1,
            }
        )

    _, stderr = run_script(monkeypatch, "list_services.py", [], fake_get=fake_get, scripts_dir=DATASOURCE_SCRIPTS_DIR)
    payload = extract_meta(stderr, "CATALOG_META")
    params = payload["catalogs"][0]["params"]

    assert params == [
        {
            "key": "templateId",
            "label": "Template",
            "required": False,
            "source": None,
            "defaultValue": "vm-531",
        }
    ]


def test_list_applications_emits_meta_and_selection_prompt(monkeypatch):
    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/groups"
        assert params["businessGroupIds"] == "bg-1"
        return FakeResponse(
            {
                "content": [
                    {"id": "app-1", "name": "Project A", "description": "A team app"},
                    {"id": "app-2", "name": "Project B", "description": ""},
                ],
                "totalElements": 2,
            }
        )

    stdout, stderr = run_script(monkeypatch, "list_applications.py", ["bg-1"], fake_get=fake_get)
    payload = extract_meta(stderr, "APPLICATION_META")

    assert "Found 2 application(s):" in stdout
    assert "请选择应用（输入编号）：" in stdout
    assert "Project A" in stdout
    assert payload[0]["id"] == "app-1"
    assert payload[0]["description"] == "A team app"
    assert payload[1]["name"] == "Project B"


def test_list_components_emits_os_type(monkeypatch):
    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/components"
        assert params == {"resourceType": "resource.windows"}
        return FakeResponse(
            [
                {
                    "id": "component-1",
                    "nameZh": "Windows Compute",
                    "model": {
                        "typeName": "cloudchef.nodes.WindowsCompute",
                        "cloudEntryTypeIds": "vsphere",
                        "osType": "Windows",
                    },
                }
            ]
        )

    stdout, stderr = run_script(
        monkeypatch,
        "list_components.py",
        ["resource.windows"],
        fake_get=fake_get,
    )
    payload = extract_meta(stderr, "COMPONENT_META")

    assert "Component: Windows Compute" in stdout
    assert payload["typeName"] == "cloudchef.nodes.WindowsCompute"
    assert payload["osType"] == "Windows"
    assert payload["cloudEntryTypeIds"] == "vsphere"


def test_list_components_rejects_catalog_id_like_input(monkeypatch):
    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=test-token")
    monkeypatch.setattr(sys, "argv", ["list_components.py", "BUILD-IN-CATALOG-LINUX-VM"])

    stdout = io.StringIO()
    stderr = io.StringIO()
    script_path = SCRIPTS_DIR / "list_components.py"
    spec = importlib.util.spec_from_file_location("test_list_components_bad_arg_module", script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                spec.loader.exec_module(module)
        except SystemExit as exc:
            assert exc.code == 1
    finally:
        sys.modules.pop(spec.name, None)

    output = stdout.getvalue()
    assert "only accepts source_key" in output
    assert "Do NOT pass catalog_id" in output


def test_list_images_builds_dynamic_body_from_selected_resource_pool(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, verify=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse(
            {
                "content": [
                    {"id": "img-1", "nameZh": "CentOS 7"},
                ]
            }
        )

    stdout, stderr = run_script(
        monkeypatch,
        "list_images.py",
        ["rb-1", "lt-1", "yacmp:cloudentry:type:vsphere"],
        fake_post=fake_post,
    )
    payload = extract_meta(stderr, "IMAGE_META")

    assert captured["url"] == "https://cmp.example.com/platform-api/cloudprovider?action=queryCloudResource"
    assert captured["json"]["cloudResourceType"] == "yacmp:cloudentry:type:vsphere::images"
    assert captured["json"]["queryProperties"] == {
        "resourceBundleId": "rb-1",
        "logicTemplateId": "lt-1",
        "queryResourceBundle": False,
    }
    assert "instanceType" not in captured["json"]["queryProperties"]
    assert "Found 1 image(s):" in stdout
    assert payload[0]["id"] == "img-1"
    assert payload[0]["name"] == "CentOS 7"


def test_list_images_normalizes_shorthand_platform_and_allows_overrides(monkeypatch):
    captured = {}
    monkeypatch.setenv("IMAGE_QUERY_LIMIT", "99")
    monkeypatch.setenv("IMAGE_QUERY_PROPERTIES_JSON", json.dumps({"region": "cn-east-1"}))
    monkeypatch.setenv(
        "IMAGE_QUERY_BODY_JSON",
        json.dumps(
            {
                "businessGroupId": "bg-1",
                "queryProperties": {
                    "providerScope": "tenant-default",
                },
            }
        ),
    )

    def fake_post(url, headers=None, json=None, verify=None, timeout=None):
        captured["json"] = json
        return FakeResponse(
            {
                "content": [
                    {"id": "img-2", "name": "Ubuntu 22.04"},
                ]
            }
        )

    stdout, stderr = run_script(
        monkeypatch,
        "list_images.py",
        ["rb-2", "lt-2", "vsphere"],
        fake_post=fake_post,
    )
    payload = extract_meta(stderr, "IMAGE_META")

    assert captured["json"]["cloudResourceType"] == "yacmp:cloudentry:type:vsphere::images"
    assert captured["json"]["businessGroupId"] == "bg-1"
    assert captured["json"]["limit"] == 99
    assert captured["json"]["queryProperties"] == {
        "resourceBundleId": "rb-2",
        "logicTemplateId": "lt-2",
        "queryResourceBundle": False,
        "region": "cn-east-1",
        "providerScope": "tenant-default",
    }
    assert "Found 1 image(s):" in stdout
    assert payload[0]["id"] == "img-2"
    assert payload[0]["name"] == "Ubuntu 22.04"
