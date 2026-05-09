# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

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
REQUEST_SCRIPTS_DIR = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "request"
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


def run_main_script(monkeypatch, script_path: Path, argv: list[str], *, fake_get=None, fake_post=None):
    module_name = f"test_{script_path.stem}_main_module"

    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=test-token")
    monkeypatch.setattr(requests, "get", fake_get or _unexpected_http_call)
    monkeypatch.setattr(requests, "post", fake_post or _unexpected_http_call)

    stdout = io.StringIO()
    stderr = io.StringIO()
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exit_code = 0
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            spec.loader.exec_module(module)
            exit_code = module.main(argv)
    finally:
        sys.modules.pop(module_name, None)

    return exit_code, stdout.getvalue(), stderr.getvalue()


def test_list_services_preserves_generated_markdown_resource_specs(monkeypatch):
    instructions = """
# Request Parameter Instructions

catalog:
  id: "catalog-slb"
  source_key: "resource.iaas.network.load_balancer.alicloud_slb"
  component_type: "resource.iaas.network.load_balancer.alicloud_slb"
  service_category: "CLOUD_COMPONENT_SERVICE"
top_level_required:
- "catalogId"
- "businessGroupId"
- "name"
top_level_fields:
  name:
    type: "string"
    required: true
    ask: true
params:
  workComments:
    type: "string"
    required: true
    default_value: "222333"
  requestType:
    type: "string"
    required: false
    default_value: "normal"
    options:
    - id: "normal"
      label: "Normal"
    - id: "urgent"
      label: "Urgent"
resource_specs:
- node: "alicloud_slb"
  type: "resource.iaas.network.load_balancer.alicloud_slb"
  resourceBundleId:
    type: "string"
    required: true
    default_value: "rb-1"
  resourceBundleParams:
    available_zone_id:
      type: "string"
      required: true
      default_value: "cn-shanghai-a"
    resource_group_id:
      type: "string"
      required: false
  resourceBundleTags:
    type: "array"
    required: false
    default_value:
    - "env:prod"
  credentialUser:
    type: "string"
    required: true
    ask: true
  systemDisk:
    type: "object"
    required: true
    default_value:
      size: 50
  networkId:
    type: "string"
    required: true
    default_value: "vsw-1"
  securityGroupIds:
    type: "array"
    required: false
    default_value:
    - "sg-1"
  params:
    InstanceChargeType:
      type: "string"
      required: true
      default_value: "PayByCLCU"
    AddressType:
      type: "string"
      required: true
      default_value: "intranet"
      options:
      - id: "internet"
        label: "公网"
      - id: "intranet"
        label: "私网"
    VpcId:
      type: "string"
      required: true
      default_value: "vpc-1"
      when: "AddressType == intranet"

# Request Instructions

Build from the request parameter section only.

# Preapproval Instructions

This section is not for request building.
""".strip()

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/published"
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "catalog-slb",
                        "nameZh": "Load Balancer",
                        "sourceKey": "resource.iaas.network.load_balancer.alicloud_slb",
                        "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                        "instructions": instructions,
                    }
                ],
                "totalElements": 1,
            }
        )

    stdout, stderr = run_script(
        monkeypatch,
        "list_services.py",
        [],
        fake_get=fake_get,
        scripts_dir=DATASOURCE_SCRIPTS_DIR,
    )
    payload = extract_meta(stderr, "CATALOG_META")
    catalog = payload["catalogs"][0]
    spec = catalog["instructions"]["resourceSpecs"][0]

    assert "Found 1 published catalog(s)." in stdout
    assert catalog["node"] == "alicloud_slb"
    assert catalog["type"] == "resource.iaas.network.load_balancer.alicloud_slb"
    assert catalog["componentType"] == "resource.iaas.network.load_balancer.alicloud_slb"
    assert "params" not in catalog
    assert catalog["instructions"]["topLevelRequired"] == ["catalogId", "businessGroupId", "name"]
    assert catalog["instructions"]["requestInstructions"] == "Build from the request parameter section only."
    assert catalog["instructions"]["topLevelFields"]["name"]["ask"] is True
    assert catalog["instructions"]["params"]["workComments"]["defaultValue"] == "222333"
    assert catalog["instructions"]["params"]["workComments"]["location"] == "rootParams"
    assert catalog["instructions"]["params"]["requestType"]["options"] == [
        {"id": "normal", "label": "Normal"},
        {"id": "urgent", "label": "Urgent"},
    ]
    assert spec["node"] == "alicloud_slb"
    assert spec["type"] == "resource.iaas.network.load_balancer.alicloud_slb"
    assert "componentType" not in spec
    assert spec["resourceBundleId"]["defaultValue"] == "rb-1"
    assert spec["resourceBundleParams"]["available_zone_id"]["defaultValue"] == "cn-shanghai-a"
    assert spec["resourceBundleParams"]["resource_group_id"]["required"] is False
    assert spec["resourceBundleTags"]["defaultValue"] == ["env:prod"]
    assert "fields" not in spec
    assert spec["credentialUser"]["location"] == "resourceSpecFields"
    assert spec["credentialUser"]["ask"] is True
    assert spec["systemDisk"]["defaultValue"] == {"size": 50}
    assert spec["networkId"]["defaultValue"] == "vsw-1"
    assert spec["securityGroupIds"]["defaultValue"] == ["sg-1"]
    assert spec["params"]["InstanceChargeType"]["defaultValue"] == "PayByCLCU"
    assert spec["params"]["AddressType"]["defaultValue"] == "intranet"
    assert spec["params"]["AddressType"]["options"] == [
        {"id": "internet", "label": "公网"},
        {"id": "intranet", "label": "私网"},
    ]
    assert spec["params"]["VpcId"]["when"] == "AddressType == intranet"


def test_list_services_ignores_old_json_instruction_payloads(monkeypatch):
    instructions = json.dumps(
        {
            "parameters": [
                {"key": "cpu", "required": True, "defaultValue": 2},
            ]
        },
        ensure_ascii=False,
    )

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/published"
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "catalog-old-json",
                        "nameZh": "Old JSON Catalog",
                        "sourceKey": "resource.iaas.machine.instance.abstract",
                        "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                        "instructions": instructions,
                    }
                ],
                "totalElements": 1,
            }
        )

    _, stderr = run_script(
        monkeypatch,
        "list_services.py",
        [],
        fake_get=fake_get,
        scripts_dir=DATASOURCE_SCRIPTS_DIR,
    )
    payload = extract_meta(stderr, "CATALOG_META")
    catalog = payload["catalogs"][0]

    assert "instructions" not in catalog
    assert "params" not in catalog


def test_list_services_keeps_boolean_and_numeric_markdown_defaults(monkeypatch):
    instructions = """
# Request Parameter Instructions

resource_specs:
- node: "EIP"
  type: "resource.iaas.network.floating_ip.eip.aliyun"
  params:
    AllocateEIP:
      type: "boolean"
      required: false
      default_value: false
    Bandwidth:
      type: "number"
      required: true
      default_value: 5
      when: "AllocateEIP == true"
""".strip()

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/published"
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "catalog-eip",
                        "nameZh": "EIP",
                        "sourceKey": "resource.iaas.network.floating_ip.eip.aliyun",
                        "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                        "instructions": instructions,
                    }
                ],
                "totalElements": 1,
            }
        )

    _, stderr = run_script(
        monkeypatch,
        "list_services.py",
        [],
        fake_get=fake_get,
        scripts_dir=DATASOURCE_SCRIPTS_DIR,
    )
    payload = extract_meta(stderr, "CATALOG_META")
    params = payload["catalogs"][0]["instructions"]["resourceSpecs"][0]["params"]

    assert params["AllocateEIP"]["defaultValue"] is False
    assert params["Bandwidth"]["defaultValue"] == 5
    assert params["Bandwidth"]["when"] == "AllocateEIP == true"


def test_list_services_does_not_parse_legacy_front_matter_instructions(monkeypatch):
    instructions = """
---
resource_specs:
- node: "EIP"
  type: "resource.iaas.network.floating_ip.eip.aliyun"
---
""".strip()

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/published"
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "catalog-legacy",
                        "nameZh": "Legacy",
                        "sourceKey": "resource.iaas.network.floating_ip.eip.aliyun",
                        "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                        "instructions": instructions,
                    }
                ],
                "totalElements": 1,
            }
        )

    _, stderr = run_script(
        monkeypatch,
        "list_services.py",
        [],
        fake_get=fake_get,
        scripts_dir=DATASOURCE_SCRIPTS_DIR,
    )
    payload = extract_meta(stderr, "CATALOG_META")

    assert "instructions" not in payload["catalogs"][0]


def test_list_services_derives_resource_type_from_blueprint_when_markdown_is_empty(monkeypatch):
    main_yaml = """
tosca_definitions_version: cloudify_dsl_1_3
node_templates:
  Compute:
    type: cloudchef.nodes.Compute
    properties:
      tags: []
  Network:
    type: cloudchef.nodes.Network
""".strip()

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/published"
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "catalog-linux",
                        "name": "Linux VM",
                        "sourceKey": "resource.iaas.machine.instance.abstract",
                        "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                        "type": "APPLICATION",
                        "instructions": "",
                        "blueprint": {
                            "id": "bp-1",
                            "name": "Linux VM",
                            "type": "OWNED_BY_CATALOG",
                            "mainYaml": main_yaml,
                        },
                    }
                ],
                "totalElements": 1,
            }
        )

    _, stderr = run_script(
        monkeypatch,
        "list_services.py",
        [],
        fake_get=fake_get,
        scripts_dir=DATASOURCE_SCRIPTS_DIR,
    )
    payload = extract_meta(stderr, "CATALOG_META")
    catalog = payload["catalogs"][0]

    assert catalog["catalogType"] == "APPLICATION"
    assert "instructions" not in catalog
    assert catalog["node"] == "Compute"
    assert catalog["type"] == "cloudchef.nodes.Compute"


def test_list_services_prefers_instruction_type_over_blueprint_resource_type(monkeypatch):
    instructions = """
# Request Parameter Instructions

resource_specs:
- node: "Database"
  type: "cloudchef.nodes.Database"
""".strip()
    main_yaml = """
node_templates:
  Compute:
    type: cloudchef.nodes.Compute
""".strip()

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/published"
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "catalog-db",
                        "name": "Database",
                        "sourceKey": "resource.paas.database",
                        "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                        "type": "APPLICATION",
                        "instructions": instructions,
                        "blueprint": {"mainYaml": main_yaml},
                    }
                ],
                "totalElements": 1,
            }
        )

    _, stderr = run_script(
        monkeypatch,
        "list_services.py",
        [],
        fake_get=fake_get,
        scripts_dir=DATASOURCE_SCRIPTS_DIR,
    )
    payload = extract_meta(stderr, "CATALOG_META")
    catalog = payload["catalogs"][0]

    assert catalog["catalogType"] == "APPLICATION"
    assert catalog["node"] == "Database"
    assert catalog["type"] == "cloudchef.nodes.Database"


def test_list_resource_bundles_uses_request_flow_filters(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "rb-1",
                        "name": "aliyun资源池",
                        "businessGroupId": "bg-1",
                        "cloudEntryTypeId": "yacmp:cloudentry:type:aliyun",
                        "cloudEntryId": "ce-1",
                        "regionId": "cn-shanghai",
                        "privateCloudEntry": False,
                        "facets": ["FACET_ENV:dev"],
                    }
                ]
            }
        )

    exit_code, stdout, _ = run_main_script(
        monkeypatch,
        REQUEST_SCRIPTS_DIR / "list_resource_bundles.py",
        [
            "bg-1",
            "resource.iaas.machine.instance.abstract",
            "cloudchef.nodes.Compute",
            "--cloud-entry-type-id",
            "yacmp:cloudentry:type:aliyun",
        ],
        fake_get=fake_get,
    )
    payload = extract_meta(stdout, "RESOURCE_BUNDLE_META")

    assert exit_code == 0
    assert captured["url"] == "https://cmp.example.com/platform-api/resource-bundles"
    assert captured["params"] == {
        "businessGroupId": "bg-1",
        "cloudEntryTypeId": "yacmp:cloudentry:type:aliyun",
        "componentType": "resource.iaas.machine.instance.abstract",
        "enabled": "true",
        "nodeType": "cloudchef.nodes.Compute",
        "readOnly": "false",
        "strategy": "RB_POLICY_STATIC",
    }
    assert "Found 1 resource pool(s)" in stdout
    assert payload[0]["id"] == "rb-1"
    assert payload[0]["facets"] == ["FACET_ENV:dev"]


def test_list_facets_outputs_only_compact_request_metadata(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "raw-facet-id",
                        "key": "FACET_ENV",
                        "nameZh": "资源环境",
                        "aspects": ["RESOURCE_BUNDLE", "NETWORK"],
                        "createdBy": "ROLE_SOLUTION_USER",
                        "lockVersion": 7,
                        "options": [
                            {
                                "id": "dev",
                                "nameZh": "开发",
                                "createdBy": "ROLE_SOLUTION_USER",
                            },
                            {
                                "key": "test",
                                "name": {"zh": "测试", "en": "Test"},
                                "deleted": False,
                            },
                        ],
                    }
                ]
            }
        )

    exit_code, stdout, _ = run_main_script(
        monkeypatch,
        REQUEST_SCRIPTS_DIR / "list_facets.py",
        ["bg-1", "--node-type", "resource.iaas.network.load_balancer.alicloud_slb"],
        fake_get=fake_get,
    )
    payload = extract_meta(stdout, "FACET_META")

    assert exit_code == 0
    assert captured["url"] == "https://cmp.example.com/platform-api/resource-bundles/available-facets"
    assert captured["params"] == {
        "businessGroupId": "bg-1",
        "cloudEntryId": "",
        "nodeType": "resource.iaas.network.load_balancer.alicloud_slb",
    }
    assert payload == [
        {
            "key": "FACET_ENV",
            "label": "资源环境",
            "options": [
                {"key": "dev", "label": "开发"},
                {"key": "test", "label": "测试"},
            ],
        }
    ]
    assert "raw-facet-id" not in stdout
    assert "createdBy" not in stdout
    assert "aspects" not in stdout
    assert "lockVersion" not in stdout


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
