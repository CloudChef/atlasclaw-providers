# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Contracts for Provider-owned Context matching and external resolution."""

from __future__ import annotations

import json
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
ROUTES_PATH = PROVIDER_ROOT / "assistant_context" / "routes.json"

def test_routes_match_context_to_existing_skills_with_one_provider_resolver() -> None:
    manifest = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    assert set(manifest) == {
        "schema_version",
        "provider_type",
        "context_resolver",
        "routes",
    }
    assert manifest["schema_version"] == 1
    assert manifest["provider_type"] == "smartcmp"
    assert manifest["context_resolver"] == {
        "entrypoint": "assistant_context/resolve.py"
    }
    assert (PROVIDER_ROOT / manifest["context_resolver"]["entrypoint"]).is_file()
    routes = manifest["routes"]
    assert [
        (route["id"], route["match"]["path_template"], route["result"]["skill_ref"])
        for route in routes
    ] == [
        (
            "pending-approval-detail",
            "/main/new-application/pendingApproval/{approval_type}/{approval_id}",
            "smartcmp:approval",
        ),
        ("catalog-request", "/main/catalog-ui/request/{catalog_id}", "smartcmp:request"),
        (
            "request-detail",
            "/main/new-process/myApplication/{application_type}/{request_id}",
            "smartcmp:request",
        ),
        ("cloud-resource-detail", "/main/cloud-resource/{resource_id}", "smartcmp:resource"),
        (
            "virtual-machine-detail",
            "/main/virtual-machines/{resource_id}/details",
            "smartcmp:resource",
        ),
    ]
    for route in routes:
        assert set(route) == {"id", "priority", "match", "result"}
        assert set(route["match"]) == {"path_template"}
        assert set(route["result"]) == {
            "page_type",
            "object_type",
            "skill_ref",
        }
        skill_name = route["result"]["skill_ref"].split(":", 1)[1]
        assert (PROVIDER_ROOT / "skills" / skill_name / "SKILL.md").is_file()
