# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "form-designer-agent"
    / "scripts"
    / "resolve_catalog_fields.py"
)


def _load_module():
    module_name = "test_resolve_catalog_fields_script_module"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def _run_script(detail: dict, labels: str):
    module = _load_module()
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main([json.dumps(detail, ensure_ascii=False), labels])
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _extract_meta(stderr: str) -> dict:
    payload = stderr.split("##CATALOG_FIELD_RESOLUTION_META_START##\n", 1)[1].split(
        "\n##CATALOG_FIELD_RESOLUTION_META_END##",
        1,
    )[0]
    return json.loads(payload)


def test_resolve_catalog_fields_maps_payload_labels_to_keys() -> None:
    detail = {
        "id": "catalog-ip",
        "name": "IP Request",
        "hasCatalogPayloadFields": True,
        "catalogPayloadFields": {
            "applicationSystem": {
                "key": "applicationSystem",
                "label": "Application System",
                "type": "string",
            },
            "costCenter": {"key": "costCenter", "label": "Cost Center", "type": "string"},
        },
        "catalogFieldKeys": {"payloadFields": ["applicationSystem", "costCenter"]},
    }

    exit_code, stdout, stderr = _run_script(detail, "Application System,Cost Center")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert "Resolved Catalog Fields: Application System=applicationSystem,Cost Center=costCenter" in stdout
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == "Application System=applicationSystem,Cost Center=costCenter"
    assert meta["mappings"] == [
        {"label": "Application System", "key": "applicationSystem", "source": "catalogPayloadFields"},
        {"label": "Cost Center", "key": "costCenter", "source": "catalogPayloadFields"},
    ]
    assert meta["missingLabels"] == []
    assert meta["nextTool"] == "smartcmp_generate_catalog_context_form"


def test_resolve_catalog_fields_maps_request_instruction_fields() -> None:
    detail = {
        "id": "catalog-eip",
        "name": "EIP",
        "hasRequestParameterInstructions": True,
        "instructions": {
            "resourceSpecs": [
                {
                    "node": "EIP",
                    "type": "resource.example.eip",
                    "params": {
                        "InstanceChargeType": {"key": "InstanceChargeType", "label": "Billing Type"},
                        "Bandwidth": {"key": "Bandwidth", "label": "Bandwidth", "type": "number"},
                    },
                }
            ]
        },
    }

    exit_code, _, stderr = _run_script(detail, "Billing Type,Bandwidth")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == "Billing Type=InstanceChargeType,Bandwidth=Bandwidth"
    assert meta["mappings"][0]["source"] == "instructions.resourceSpecs.params"


def test_resolve_catalog_fields_maps_chinese_eip_labels_to_instruction_keys() -> None:
    detail = {
        "id": "catalog-eip",
        "name": "EIP",
        "hasRequestParameterInstructions": True,
        "instructions": {
            "resourceSpecs": [
                {
                    "node": "EIP",
                    "type": "resource.iaas.network.floating_ip.eip.aliyun",
                    "params": {
                        "AllocateEIP": {
                            "key": "AllocateEIP",
                            "label": "AllocateEIP",
                            "type": "boolean",
                        },
                        "InternetChargeType": {
                            "key": "InternetChargeType",
                            "label": "InternetChargeType",
                            "description": "计费类型",
                            "type": "string",
                            "when": (
                                "AllocateEIP == true && "
                                "resource_bundle_config.privateCloudEntry == false"
                            ),
                        },
                        "Netmode": {"key": "Netmode", "label": "Netmode", "type": "string"},
                        "Bandwidth": {
                            "key": "Bandwidth",
                            "label": "Bandwidth",
                            "description": "带宽",
                            "type": "number",
                        },
                    },
                }
            ]
        },
    }

    exit_code, _, stderr = _run_script(detail, "计费类型,带宽")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == "计费类型=InternetChargeType,带宽=Bandwidth"
    assert meta["missingLabels"] == []
    assert meta["mappings"] == [
        {
            "label": "计费类型",
            "key": "InternetChargeType",
            "source": "instructions.resourceSpecs.params",
        },
        {
            "label": "带宽",
            "key": "Bandwidth",
            "source": "instructions.resourceSpecs.params",
        },
    ]
    assert "call smartcmp_generate_catalog_context_form immediately" in meta["nextStep"]
    assert "do not ask whether the composed field should be visible" in meta["nextStep"]


def test_resolve_catalog_fields_does_not_guess_translated_labels_without_evidence() -> None:
    detail = {
        "id": "catalog-eip",
        "name": "EIP",
        "instructions": {
            "resourceSpecs": [
                {
                    "node": "EIP",
                    "params": {
                        "InternetChargeType": {
                            "key": "InternetChargeType",
                            "label": "InternetChargeType",
                        },
                        "Bandwidth": {"key": "Bandwidth", "label": "Bandwidth"},
                    },
                }
            ]
        },
    }

    exit_code, _, stderr = _run_script(detail, "计费类型,带宽")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is False
    assert meta["catalogContextFields"] == ""
    assert meta["missingLabels"] == ["计费类型", "带宽"]


def test_resolve_catalog_fields_warns_when_requested_labels_are_backend_keys() -> None:
    detail = {
        "id": "catalog-eip",
        "name": "EIP",
        "instructions": {
            "resourceSpecs": [
                {
                    "node": "EIP",
                    "params": {
                        "InternetChargeType": {
                            "key": "InternetChargeType",
                            "label": "InternetChargeType",
                        },
                        "Bandwidth": {"key": "Bandwidth", "label": "Bandwidth"},
                    },
                }
            ]
        },
    }

    exit_code, stdout, stderr = _run_script(detail, "InternetChargeType,Bandwidth")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == "InternetChargeType=InternetChargeType,Bandwidth=Bandwidth"
    assert meta["backendKeyLabelWarnings"] == ["Bandwidth", "InternetChargeType"]
    assert "Requested labels look like backend keys" in stdout


def test_resolve_catalog_fields_maps_linux_compute_spec_to_flavor_id() -> None:
    detail = {
        "id": "f3a4149b-cfbf-446a-a340-512a304014f2",
        "name": "Linux VM",
        "hasRequestParameterInstructions": True,
        "instructions": {
            "componentType": "resource.iaas.machine.instance.abstract",
            "resourceSpecs": [
                {
                    "node": "Compute",
                    "type": "cloudchef.nodes.Compute",
                    "computeProfileId": {
                        "key": "computeProfileId",
                        "label": "computeProfileId",
                        "type": "string",
                        "location": "resourceSpecFields",
                        "node": "Compute",
                    },
                    "flavorId": {
                        "key": "flavorId",
                        "label": "flavorId",
                        "description": "计算规格",
                        "type": "string",
                        "location": "resourceSpecFields",
                        "node": "Compute",
                    },
                    "logicTemplateId": {
                        "key": "logicTemplateId",
                        "label": "logicTemplateId",
                        "type": "string",
                        "location": "resourceSpecFields",
                        "node": "Compute",
                    },
                }
            ],
        },
    }

    exit_code, _, stderr = _run_script(detail, "业务组,所有者,计算规格")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == (
        "业务组=@request:department,"
        "所有者=@request:owner,"
        "计算规格=flavorId"
    )
    assert meta["missingLabels"] == []
    assert meta["ambiguousLabels"] == []
    assert meta["mappings"] == [
        {
            "label": "业务组",
            "key": "@request:department",
            "source": "requestContext.fixed",
        },
        {
            "label": "所有者",
            "key": "@request:owner",
            "source": "requestContext.fixed",
        },
        {
            "label": "计算规格",
            "key": "flavorId",
            "source": "instructions.resourceSpecs.resourceSpecFields",
        },
    ]


def test_resolve_catalog_fields_uses_catalog_evidence_for_nonfixed_labels() -> None:
    detail = {
        "id": "catalog-ip",
        "name": "IP Request",
        "catalogPayloadFields": {
            "appSystem": {"key": "appSystem", "label": "appSystem", "description": "应用系统"},
            "environment": {"key": "environment", "label": "Environment", "description": "环境"},
        },
    }

    exit_code, _, stderr = _run_script(detail, "应用系统,环境")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == "应用系统=appSystem,环境=environment"


def test_resolve_catalog_fields_stops_when_catalog_has_no_field_evidence() -> None:
    detail = {
        "id": "catalog-ip",
        "name": "IP Request",
        "hasRequestParameterInstructions": False,
        "hasCatalogPayloadFields": False,
    }

    exit_code, stdout, stderr = _run_script(detail, "Application System,Environment")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert "Catalog fields unresolved" in stdout
    assert meta["canGenerateCatalogContextForm"] is False
    assert meta["catalogContextFields"] == ""
    assert meta["missingLabels"] == ["Application System", "Environment"]
    assert meta["nextTool"] == ""


def test_resolve_catalog_fields_maps_catalog_field_from_catalog_evidence() -> None:
    detail = {
        "id": "catalog-oss",
        "name": "OSS",
        "instructions": {
            "resourceSpecs": [
                {
                    "node": "OSS",
                    "type": "resource.example.oss",
                    "resourceBundleParams": {
                        "resource_group_id": {
                            "key": "resource_group_id",
                            "label": "resource_group_id",
                            "description": "资源组 ID",
                        },
                        "available_zone_id": {
                            "key": "available_zone_id",
                            "label": "available_zone_id",
                        },
                    },
                }
            ]
        },
    }

    exit_code, _, stderr = _run_script(detail, "资源组")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == "资源组=resource_group_id"
    assert meta["mappings"] == [
        {
            "label": "资源组",
            "key": "resource_group_id",
            "source": "instructions.resourceSpecs.resourceBundleParams",
        }
    ]


def test_resolve_catalog_fields_keeps_fixed_context_in_mixed_catalog_mapping() -> None:
    detail = {
        "id": "catalog-oss",
        "name": "OSS",
        "instructions": {
            "resourceSpecs": [
                {
                    "node": "OSS",
                    "type": "resource.example.oss",
                    "resourceBundleParams": {
                        "resource_group_id": {
                            "key": "resource_group_id",
                            "label": "resource_group_id",
                            "description": "资源组 ID",
                        },
                    },
                }
            ]
        },
    }

    labels = "业务组,所有者,资源组"
    exit_code, _, stderr = _run_script(detail, labels)

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == (
        "业务组=@request:department,"
        "所有者=@request:owner,"
        "资源组=resource_group_id"
    )
    assert meta["mappings"] == [
        {
            "label": "业务组",
            "key": "@request:department",
            "source": "requestContext.fixed",
        },
        {
            "label": "所有者",
            "key": "@request:owner",
            "source": "requestContext.fixed",
        },
        {
            "label": "资源组",
            "key": "resource_group_id",
            "source": "instructions.resourceSpecs.resourceBundleParams",
        },
    ]


def test_resolve_catalog_fields_does_not_hardcode_catalog_specific_aliases() -> None:
    detail = {
        "id": "catalog-oss",
        "name": "OSS",
        "instructions": {
            "resourceSpecs": [
                {
                    "node": "OSS",
                    "type": "resource.example.oss",
                    "resourceBundleParams": {
                        "resource_group_id": {
                            "key": "resource_group_id",
                            "label": "resource_group_id",
                        },
                    },
                }
            ]
        },
    }

    exit_code, _, stderr = _run_script(detail, "资源组")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is False
    assert meta["missingLabels"] == ["资源组"]
    assert meta["candidateFields"][0]["key"] == "resource_group_id"
