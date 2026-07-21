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
    / "shared"
    / "scripts"
    / "get_catalog_detail.py"
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _load_module(monkeypatch):
    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=token")
    spec = importlib.util.spec_from_file_location("smartcmp_get_catalog_detail_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _extract_meta(stderr: str) -> dict:
    payload = stderr.split("##CATALOG_DETAIL_META_START##\n", 1)[1].split(
        "\n##CATALOG_DETAIL_META_END##",
        1,
    )[0]
    return json.loads(payload)


def test_catalog_detail_fetches_by_id_and_extracts_preapproval_section(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    instructions = """
# Request Parameter Instructions

catalog:
  id: "catalog-1"

# Pre Approval Instructions

Approve only when the requester selects the dev environment.

# Request Instructions

Use the request parameter contract.
""".strip()

    def fake_get(url, headers=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/catalog-1"
        assert timeout == 60
        return _FakeResponse(
            {
                "id": "catalog-1",
                "name": "Linux VM",
                "sourceKey": "resource.iaas.machine.instance.abstract",
                "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                "type": "CLOUD_COMPONENT",
                "status": "PUBLISHED",
                "instructions": instructions,
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["catalog-1"])

    assert exit_code == 0
    assert "Catalog Detail: Linux VM" in stdout.getvalue()
    meta = _extract_meta(stderr.getvalue())
    assert meta["id"] == "catalog-1"
    assert meta["object_type"] == "catalog"
    assert meta["object_id"] == "catalog-1"
    assert meta["object_name"] == "Linux VM"
    assert [action["action_id"] for action in meta["object_actions"]] == [
        "open_detail",
        "request",
    ]
    assert meta["hasPreApprovalInstructions"] is True
    assert meta["preApprovalInstructionHeading"] == "# Pre Approval Instructions"
    assert meta["preApprovalInstructions"] == "Approve only when the requester selects the dev environment."
    assert "Request Instructions" not in meta["preApprovalInstructions"]


def test_catalog_detail_reports_missing_preapproval_section(monkeypatch) -> None:
    module = _load_module(monkeypatch)

    def fake_get(url, headers=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/catalog-2"
        return _FakeResponse(
            {
                "id": "catalog-2",
                "name": "VPC",
                "status": "DISABLED",
                "instructions": "# Request Instructions\n\nBuild it.",
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["catalog-2"])

    assert exit_code == 0
    assert "Has Pre Approval Instructions: false" in stdout.getvalue()
    meta = _extract_meta(stderr.getvalue())
    assert meta["hasInstructions"] is True
    assert meta["hasPreApprovalInstructions"] is False
    assert "preApprovalInstructions" not in meta
