# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Approve pending approval items in SmartCMP.

Usage:
  python approve.py <request_id1> [request_id2 request_id3 ...] [--reason "Approval reason"]

Arguments:
  id1, id2, ...    SmartCMP Request IDs such as RES20260505000010
  --reason         Optional approval reason

Output:
  - Success/failure message with result details
  - ##APPROVE_RESULT_START## ... ##APPROVE_RESULT_END##
      JSON: {approved_ids, reason, status}

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python approve.py RES20260505000010
  python approve.py RES20260505000010 --reason "Approved per policy"
  python approve.py RES20260505000010 TIC20260502000003 CHG20260413000011

API Reference:
  POST /approval-activity/approve/batch?ids=<id1>,<id2>
"""
import json
import os
import sys
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from _approval_action import ApprovalResolutionError, resolve_approval_action_ids
from _approval_validation import APPROVAL_ID_FORMAT_HINT, find_invalid_approval_ids


def _load_config():
    """Load SmartCMP connection settings after local argument validation succeeds."""
    try:
        from _common import require_config
    except ImportError:
        sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "..", "shared", "scripts"))
        from _common import require_config

    return require_config()

# ── Parse arguments ───────────────────────────────────────────────────────────
# Priority: Environment variables > Command line arguments
# Framework passes tool parameters as environment variables (IDS, REASON)
ids = []
reason = ""

# Try environment variables first (from framework tool call)
env_ids = os.environ.get("IDS", "")
env_reason = os.environ.get("REASON", "")

if env_ids:
    # Split by space or comma
    ids = [x.strip() for x in env_ids.replace(",", " ").split() if x.strip()]
    reason = env_reason
else:
    # Fall back to command line arguments
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--reason" and i + 1 < len(sys.argv):
            reason = sys.argv[i + 1]
            i += 2
        elif not arg.startswith("--"):
            ids.append(arg)
            i += 1
        else:
            i += 1

if not ids:
    print("[ERROR] At least one SmartCMP Request ID is required.")
    print()
    print("Usage: python approve.py <request_id1> [request_id2 ...] [--reason \"Reason\"]")
    print("   Or: Set IDS and REASON environment variables")
    print()
    print("Get Request IDs from: python list_pending.py -> ##APPROVAL_META## requestId")
    sys.exit(1)

invalid_ids = find_invalid_approval_ids(ids)
if invalid_ids:
    print("[ERROR] Invalid SmartCMP Request ID(s).")
    for approval_id, reason in invalid_ids:
        print(f"  - {approval_id}: {reason}")
    print()
    print(APPROVAL_ID_FORMAT_HINT)
    sys.exit(1)

BASE_URL, AUTH_TOKEN, HEADERS, _ = _load_config()

try:
    action_ids = resolve_approval_action_ids(ids, base_url=BASE_URL, headers=HEADERS)
except ApprovalResolutionError as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Request failed while resolving Request ID(s): {e}")
    print("Re-list pending approvals and retry with the user-facing Request ID if it is still pending.")
    sys.exit(1)

headers = HEADERS

# ── Approve request ───────────────────────────────────────────────────────────
url = f"{BASE_URL}/approval-activity/approve/batch"
params = {"ids": ",".join(action_ids)}
body = {"reason": reason} if reason else {}

print(f"Approving {len(ids)} item(s)...")
if reason:
    print(f"Reason: {reason}")
print()

try:
    resp = requests.post(url, headers=headers, params=params, json=body, verify=False, timeout=30)
    resp.raise_for_status()
except requests.exceptions.RequestException as e:
    response = getattr(e, "response", None)
    if response is not None:
        print(f"[ERROR] Approval request failed with HTTP {response.status_code}.")
    else:
        print(f"[ERROR] Approval request failed: {type(e).__name__}")
    print("Re-list pending approvals and retry with the user-facing Request ID if it is still pending.")
    sys.exit(1)

# ── Handle response ───────────────────────────────────────────────────────────
try:
    result = resp.json()
except:
    result = resp.text

print("[SUCCESS] Approval completed.")
print()

# Show result details if available
if isinstance(result, list):
    for item in result:
        status = item.get("status") or item.get("state") or "approved"
        print(f"  Status: {status}")
elif isinstance(result, dict):
    if result.get("success") is not None:
        print(f"  Success: {result.get('success')}")
    print("  Status: approved")
else:
    print("  Status: approved")

print()
print("##APPROVE_RESULT_START##")
print(json.dumps({
    "approved_ids": ids,
    "reason": reason,
    "status": "approved",
}, ensure_ascii=False, default=str))
print("##APPROVE_RESULT_END##")
