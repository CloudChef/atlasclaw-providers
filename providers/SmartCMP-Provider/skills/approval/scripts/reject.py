# -*- coding: utf-8 -*-
"""Reject pending approval items in SmartCMP.

Usage:
  python reject.py <id1> [id2 id3 ...] [--reason "Rejection reason"]

Arguments:
  id1, id2, ...    Approval IDs from list_pending.py output (##APPROVAL_META##)
  --reason         Optional rejection reason (recommended)

Output:
  - Success/failure message with result details
  - ##REJECT_RESULT_START## ... ##REJECT_RESULT_END##
      JSON: {rejected_ids, reason, response}

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python reject.py abc123
  python reject.py abc123 --reason "Budget exceeded"
  python reject.py abc123 def456 --reason "Not aligned with policy"

API Reference:
  POST /approval-activity/reject/batch?ids=<id1>,<id2>
"""
import sys
import json
import requests

# Import shared utilities (handles URL normalization, SSL warnings)
import os
try:
    from _common import require_config
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'scripts'))
    from _common import require_config

BASE_URL, COOKIE, HEADERS = require_config()

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
    print("[ERROR] At least one approval ID is required.")
    print()
    print("Usage: python reject.py <id1> [id2 ...] [--reason \"Reason\"]")
    print("   Or: Set IDS and REASON environment variables")
    print()
    print("Get IDs from: python list_pending.py -> ##APPROVAL_META##")
    sys.exit(1)

headers = {"Content-Type": "application/json; charset=utf-8", "Cookie": COOKIE}

# ── Reject request ────────────────────────────────────────────────────────────
url = f"{BASE_URL}/approval-activity/reject/batch"
params = {"ids": ",".join(ids)}
body = {"reason": reason} if reason else {}

print(f"Rejecting {len(ids)} item(s)...")
if reason:
    print(f"Reason: {reason}")
print()

try:
    resp = requests.post(url, headers=headers, params=params, json=body, verify=False, timeout=30)
    resp.raise_for_status()
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Request failed: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"Response: {e.response.text}")
    sys.exit(1)

# ── Handle response ───────────────────────────────────────────────────────────
try:
    result = resp.json()
except:
    result = resp.text

print("[SUCCESS] Rejection completed.")
print()

# Show result details if available
if isinstance(result, list):
    for item in result:
        item_id = item.get("id", "N/A")
        status = item.get("status") or item.get("state") or "rejected"
        print(f"  ID: {item_id} → {status}")
elif isinstance(result, dict):
    if result.get("success") is not None:
        print(f"  Success: {result.get('success')}")
    if result.get("message"):
        print(f"  Message: {result.get('message')}")
else:
    print(f"  Response: {result}")

print()
print("##REJECT_RESULT_START##")
print(json.dumps({"rejected_ids": ids, "reason": reason, "response": result}, ensure_ascii=False, default=str))
print("##REJECT_RESULT_END##")
