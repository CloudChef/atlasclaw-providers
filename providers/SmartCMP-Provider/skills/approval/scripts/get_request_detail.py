# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Get SmartCMP pending approval/request detail by user-facing Request ID.

Usage:
  python get_request_detail.py <identifier> [--days N]

Arguments:
  identifier   SmartCMP user-facing Request ID, for example RES20260505000029
  --days N     Search approvals updated in the last N days (default: 90)

Output:
  - Human-readable detail summary
  - ##APPROVAL_DETAIL_META_START## ... ##APPROVAL_DETAIL_META_END##
      JSON object with structured info for agent processing
"""

from __future__ import annotations

import json
import sys
import time

import requests

try:
    from _common import require_config
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
    from _common import require_config

from _approval_object_actions import build_approval_object_actions

from _approval_context import (
    format_timestamp,
    load_pending_approval_context,
)
from _approval_validation import APPROVAL_ID_FORMAT_HINT, is_request_id


BASE_URL, AUTH_TOKEN, HEADERS, _INSTANCE = require_config()


def _parse_args() -> tuple[str, int]:
    identifier = ""
    days = 90
    args = sys.argv[1:]
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--days" and index + 1 < len(args):
            try:
                days = int(args[index + 1])
            except ValueError:
                pass
            index += 2
            continue
        if not identifier:
            identifier = arg.strip()
        index += 1
    if not identifier:
        print("[ERROR] Missing required identifier argument.")
        sys.exit(1)
    return identifier, max(days, 1)


def main() -> None:
    identifier, days = _parse_args()
    if not is_request_id(identifier):
        print("[ERROR] Invalid SmartCMP Request ID.")
        print(APPROVAL_ID_FORMAT_HINT)
        sys.exit(1)

    try:
        context = load_pending_approval_context(
            BASE_URL,
            HEADERS,
            identifier,
            days,
            request_get=requests.get,
            time_fn=time.time,
        )
    except requests.exceptions.RequestException as error:
        print(f"[ERROR] Request failed: {error}")
        sys.exit(1)

    if context is None:
        print(f"[ERROR] No pending SmartCMP approval matched identifier: {identifier} (after 5 attempts)")
        sys.exit(1)

    matched = context.item
    detail_meta = context.meta
    request_id = detail_meta["requestId"]

    print("===============================================================")
    print(f"  CMP Request Detail: {request_id or identifier}")
    print("===============================================================")
    if request_id:
        print(f"Request ID: {request_id}")
    print(f"Name: {detail_meta['name']}")
    print(f"Catalog: {detail_meta['catalogName']}")
    email_suffix = f" ({detail_meta['email']})" if detail_meta["email"] else ""
    print(f"Applicant: {detail_meta['applicant']}{email_suffix}")
    print(f"Approval Step: {detail_meta['approvalStep']}")
    print(f"Current Approver: {detail_meta['currentApprover']}")
    print(f"Created At: {format_timestamp(detail_meta['createdDate'])}")
    print(f"Updated At: {format_timestamp(detail_meta['updatedDate'])}")
    print(f"Wait Hours: {detail_meta['waitHours']}")
    print(f"Cost Estimate: {detail_meta['costEstimate']}")
    resource_specs = detail_meta["resourceSpecs"]
    if resource_specs:
        print(f"Resource Specs: {', '.join(resource_specs)}")
    if detail_meta["description"]:
        print(f"Description: {detail_meta['description']}")

    meta = dict(detail_meta)
    meta.update({
        "object_type": "approval_request",
        "object_id": request_id,
        "object_name": detail_meta["name"],
        # Detail responses have already shown the request context, so they may
        # expose analysis and decision actions in addition to opening SmartCMP.
        # The actual approve/reject side effects still go through agent prompts
        # and the dedicated scripts that validate user-facing Request IDs.
        "object_actions": build_approval_object_actions(
            BASE_URL,
            matched,
            include_detail_actions=True,
        ),
    })
    # Keep structured data out of the visible answer. AtlasClaw reads this block
    # to render generic actions and preserve exact SmartCMP identifiers.
    print("##APPROVAL_DETAIL_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
    print("##APPROVAL_DETAIL_META_END##", file=sys.stderr)


if __name__ == "__main__":
    main()
