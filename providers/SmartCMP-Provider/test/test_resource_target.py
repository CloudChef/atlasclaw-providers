# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import sys
from pathlib import Path

import pytest


SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "shared" / "scripts"
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))

from _resource_target import (  # noqa: E402
    ResourceResolutionError,
    resolve_exact_resource_name,
    resolve_single_resource,
)


def test_exact_name_resolution_scans_page_two_when_cmp_ignores_query_filter():
    calls = []
    first_page = [
        {
            "id": f"res-{index}",
            "name": f"unrelated-{index}",
            "status": "started",
            "componentType": "resource.compute",
        }
        for index in range(100)
    ]
    second_page = [
        {
            "id": "hidden-target-id",
            "name": "Prod-RDS",
            "status": "lost",
            "componentType": "resource.paas.rds.aws",
        }
    ]

    def search_page(page, size, query):
        calls.append((page, size, query))
        return (first_page if page == 1 else second_page, 101)

    resolved = resolve_exact_resource_name("Prod-RDS", search_page=search_page)

    assert resolved["id"] == "hidden-target-id"
    assert calls == [(1, 100, "Prod-RDS"), (2, 100, "Prod-RDS")]


def test_exact_name_resolution_is_case_sensitive_and_errors_hide_internal_ids():
    with pytest.raises(ResourceResolutionError) as exc_info:
        resolve_exact_resource_name(
            "prod-rds",
            search_page=lambda _page, _size, _query: [
                {
                    "id": "must-not-leak",
                    "name": "Prod-RDS",
                    "status": "lost",
                    "resourceType": "AWS RDS",
                }
            ],
        )

    message = str(exc_info.value)
    assert "must-not-leak" not in message
    assert "| # | Name | Status | Type |" in message


def test_index_requires_recent_resource_list_metadata():
    with pytest.raises(ResourceResolutionError, match="No recent resource list metadata"):
        resolve_single_resource(
            resource_id_value="",
            resource_name="",
            resource_index=2,
            directory_items=[],
            search_page=lambda _page, _size, _query: [],
        )
