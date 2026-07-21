# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Analyze one pending SmartCMP approval request without executing a decision."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import requests

try:
    from _common import request_timeout, require_config
except ImportError:
    import os

    sys.path.insert(
        0,
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "shared",
            "scripts",
        ),
    )
    from _common import request_timeout, require_config

from _approval_object_actions import build_approval_object_actions

from _approval_context import format_timestamp, load_pending_approval_context
from _approval_validation import APPROVAL_ID_FORMAT_HINT, is_request_id
from _preapproval_analysis import (
    analyze_preapproval_request,
    build_catalog_policy,
    unavailable_catalog_policy,
)


BASE_URL, AUTH_TOKEN, HEADERS, _INSTANCE = require_config()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for one read-only approval analysis."""
    parser = argparse.ArgumentParser(description="Analyze one pending SmartCMP approval request.")
    parser.add_argument("identifier", help="SmartCMP user-facing Request ID.")
    parser.add_argument("--days", type=_positive_int, default=90, help="Pending approval lookback window.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run a read-only approval analysis and emit structured action metadata."""
    args = parse_args(argv)
    identifier = args.identifier.strip()
    if not is_request_id(identifier):
        print("[ERROR] Invalid SmartCMP Request ID.")
        print(APPROVAL_ID_FORMAT_HINT)
        return 1

    try:
        context = load_pending_approval_context(
            BASE_URL,
            HEADERS,
            identifier,
            args.days,
            request_get=requests.get,
        )
    except requests.exceptions.RequestException as error:
        print(f"[ERROR] Request failed: {error}")
        return 1

    if context is None:
        print(f"[ERROR] No pending SmartCMP approval matched identifier: {identifier} (after 5 attempts)")
        return 1

    catalog_policy = _fetch_catalog_policy(context.meta.get("catalogId", ""))
    analysis = analyze_preapproval_request(context.meta, catalog_policy)
    _render_analysis(context.meta, analysis, catalog_policy)

    request_id = context.meta["requestId"]
    meta = dict(context.meta)
    meta.update(
        {
            "object_type": "approval_request",
            "object_id": request_id,
            "object_name": context.meta["name"],
            "object_actions": build_approval_object_actions(
                BASE_URL,
                context.item,
                include_detail_actions=True,
            ),
            "analysis": analysis,
            "catalogPolicy": catalog_policy,
            "readOnly": True,
        }
    )
    print("##APPROVAL_ANALYSIS_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
    print("##APPROVAL_ANALYSIS_META_END##", file=sys.stderr)
    return 0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _fetch_catalog_policy(catalog_id: str) -> dict[str, Any]:
    if not catalog_id:
        return unavailable_catalog_policy(status="missing_catalog_id")
    try:
        response = requests.get(
            f"{BASE_URL}/catalogs/{catalog_id}",
            headers=HEADERS,
            verify=False,
            timeout=request_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.exceptions.RequestException, ValueError, TypeError) as error:
        return unavailable_catalog_policy(status="unavailable", error=str(error), catalog_id=catalog_id)
    if not isinstance(payload, dict):
        return unavailable_catalog_policy(
            status="unavailable",
            error="catalog response is not a JSON object",
            catalog_id=catalog_id,
        )
    catalog = payload
    return build_catalog_policy(catalog, catalog_id)


def _render_analysis(
    detail: dict[str, Any],
    analysis: dict[str, Any],
    catalog_policy: dict[str, Any],
) -> None:
    print(f"Approval Analysis: {detail['requestId']}")
    print(f"Name: {detail['name']}")
    print(f"Catalog: {detail['catalogName']}")
    print(f"Applicant: {detail['applicant']}" + (f" ({detail['email']})" if detail.get("email") else ""))
    print(f"Approval Step: {detail['approvalStep']}")
    print(f"Current Approver: {detail['currentApprover']}")
    print(f"Created At: {format_timestamp(detail['createdDate'])}")
    print(f"Updated At: {format_timestamp(detail['updatedDate'])}")
    print(f"Wait Hours: {detail['waitHours']}")
    print(f"Cost Estimate: {detail['costEstimate']}")
    if detail.get("resourceSpecs"):
        print(f"Resource Specs: {', '.join(detail['resourceSpecs'])}")
    if detail.get("description"):
        print(f"Description: {detail['description']}")
    print("")
    print(f"Decision Guidance: {analysis['decision_guidance']}")
    print(f"Confidence: {analysis['confidence']}")
    if catalog_policy.get("hasPreApprovalInstructions"):
        print("")
        print("Catalog Pre-Approval Instructions:")
        print(str(catalog_policy.get("instructions") or ""))
    print("")
    print("Reasoning:")
    for item in analysis["reasoning"]:
        print(f"- {item}")
    if analysis["concerns"]:
        print("")
        print("Concerns:")
        for item in analysis["concerns"]:
            print(f"- {item}")
    if analysis["improvement_suggestions"]:
        print("")
        print("Improvement Suggestions:")
        for item in analysis["improvement_suggestions"]:
            print(f"- {item}")

if __name__ == "__main__":
    sys.exit(main())
