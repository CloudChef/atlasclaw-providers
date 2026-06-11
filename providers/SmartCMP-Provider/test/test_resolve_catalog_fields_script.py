# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import io
import json
import sys
import unicodedata
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


def _cjk(*codepoints: str) -> str:
    return "".join(chr(int(codepoint, 16)) for codepoint in codepoints)


def test_resolve_catalog_fields_maps_request_instruction_fields() -> None:
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
                            "description": "billing type",
                        },
                        "Bandwidth": {
                            "key": "Bandwidth",
                            "label": "Bandwidth",
                            "description": "bandwidth",
                        },
                    },
                }
            ]
        },
    }

    exit_code, stdout, stderr = _run_script(detail, "billing type,Bandwidth")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert "Resolved Catalog Fields" in stdout
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == "billing type=InternetChargeType,Bandwidth=Bandwidth"
    assert meta["nextTool"] == "smartcmp_generate_catalog_context_form"


def test_resolve_catalog_fields_does_not_map_name_owner_to_request_context() -> None:
    detail = {
        "id": "catalog-empty",
        "name": "Empty",
        "instructions": {"resourceSpecs": []},
    }

    exit_code, stdout, stderr = _run_script(detail, "name,owner")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert "Catalog fields unresolved" in stdout
    assert meta["canGenerateCatalogContextForm"] is False
    assert meta["catalogContextFields"] == ""
    assert meta["missingLabels"] == ["name", "owner"]
    assert all(not item["key"].startswith("@request:") for item in meta["mappings"])


def test_resolve_catalog_fields_maps_name_owner_only_from_catalog_evidence() -> None:
    detail = {
        "id": "catalog-user",
        "name": "User Catalog",
        "catalogPayloadFields": {
            "displayName": {"key": "displayName", "label": "name"},
            "ownerName": {"key": "ownerName", "label": "owner"},
        },
    }

    exit_code, _, stderr = _run_script(detail, "name,owner")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == "name=displayName,owner=ownerName"
    assert meta["mappings"] == [
        {"label": "name", "key": "displayName", "source": "catalogPayloadFields"},
        {"label": "owner", "key": "ownerName", "source": "catalogPayloadFields"},
    ]


def test_resolve_catalog_fields_stops_when_catalog_has_no_field_evidence() -> None:
    detail = {"id": "catalog-ip", "name": "IP Request"}

    exit_code, _, stderr = _run_script(detail, "Application System,Environment")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is False
    assert meta["missingLabels"] == ["Application System", "Environment"]
    assert meta["nextTool"] == ""


def test_resolve_catalog_fields_accepts_named_non_ascii_separators() -> None:
    detail = {
        "id": "catalog-eip",
        "name": "EIP",
        "catalogPayloadFields": {
            "InternetChargeType": {"key": "InternetChargeType", "label": "billing type"},
            "Bandwidth": {"key": "Bandwidth", "label": "bandwidth"},
        },
    }
    separator = unicodedata.lookup("FULLWIDTH COMMA")

    exit_code, _, stderr = _run_script(detail, f"billing type{separator}bandwidth")

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == "billing type=InternetChargeType,bandwidth=Bandwidth"


def test_resolve_catalog_fields_translates_common_cjk_catalog_labels() -> None:
    business_group = _cjk("4E1A", "52A1", "7EC4")
    owner = _cjk("6240", "6709", "8005")
    compute_specification = _cjk("8BA1", "7B97", "89C4", "683C")
    detail = {
        "id": "catalog-linux",
        "name": "Linux VM",
        "instructions": {
            "topLevelRequired": ["businessGroupName"],
            "topLevelFields": {
                "ownerName": {
                    "key": "ownerName",
                    "label": "owner",
                    "description": "owner",
                },
            },
            "resourceSpecs": [
                {
                    "node": "VM",
                    "params": {
                        "computeProfileId": {
                            "key": "computeProfileId",
                            "label": "compute profile",
                            "description": "flavor compute specification",
                        },
                    },
                }
            ],
        },
    }

    exit_code, _, stderr = _run_script(
        detail,
        f"{business_group},{owner},{compute_specification}",
    )

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["catalogContextFields"] == (
        "business group=businessGroupName,"
        "owner=ownerName,"
        "compute specification=computeProfileId"
    )


def test_resolve_catalog_fields_prefers_exact_cjk_payload_labels_over_semantics() -> None:
    business_group = _cjk("4E1A", "52A1", "7EC4")
    owner = _cjk("6240", "6709", "8005")
    compute_specification = _cjk("8BA1", "7B97", "89C4", "683C")
    flavor_specification = _cjk("5957", "9910", "89C4", "683C")
    detail = {
        "id": "catalog-linux",
        "name": "Linux VM",
        "catalogPayloadFields": {
            "ownerName": {"key": "ownerName", "label": owner},
            "computeProfileId": {"key": "computeProfileId", "label": compute_specification},
            "flavorId": {"key": "flavorId", "label": flavor_specification},
        },
        "instructions": {
            "topLevelRequired": ["businessGroupName"],
            "resourceSpecs": [
                {
                    "node": "VM",
                    "params": {
                        "computeProfileId": {
                            "key": "computeProfileId",
                            "label": "compute profile id",
                            "description": "compute specification id",
                        },
                        "flavorId": {
                            "key": "flavorId",
                            "label": "flavor id",
                            "description": "flavor specification id",
                        },
                    },
                }
            ],
        },
    }

    exit_code, _, stderr = _run_script(
        detail,
        f"{business_group},{owner},{compute_specification}",
    )

    meta = _extract_meta(stderr)
    assert exit_code == 0
    assert meta["canGenerateCatalogContextForm"] is True
    assert meta["ambiguousLabels"] == []
    assert meta["missingLabels"] == []
    assert meta["catalogContextFields"] == (
        "business group=businessGroupName,"
        "owner=ownerName,"
        "compute specification=computeProfileId"
    )
