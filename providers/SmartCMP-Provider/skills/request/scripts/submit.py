# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Submit a service request to SmartCMP.

Usage:
  python submit.py --file <json_file>
  python submit.py --json '<json_string>'

Arguments:
  --file, -f    Path to JSON file containing request body (recommended)
  --json, -j    JSON string (not recommended in PowerShell due to encoding)

Output:
  - Request ID and State for each submitted request

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python submit.py --file request_body.json
  python submit.py -f ./my_request.json

API Reference:
  POST /generic-request/submit
"""
import sys
import json
import os
import argparse
import time
import requests

# Import shared utilities (handles URL normalization, SSL warnings)
try:
    from _common import require_config, create_headers
except ImportError:
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'scripts'))
    from _common import require_config, create_headers

BASE_URL, AUTH_TOKEN, HEADERS, _ = require_config()

_VERIFY_ATTEMPTS = max(1, int(os.environ.get("CMP_SUBMIT_VERIFY_ATTEMPTS", "8") or "8"))
_VERIFY_INTERVAL_SECONDS = max(
    0.0,
    float(os.environ.get("CMP_SUBMIT_VERIFY_INTERVAL_SECONDS", "1") or "1"),
)


def _normalize_value(value: object) -> str:
    normalized = str(value or "").strip()
    return normalized


def _unwrap_value(value: object) -> object:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _normalize_list(values: object) -> list[str]:
    if isinstance(values, list):
        items = values
    elif values in (None, "", {}, ()):
        items = []
    else:
        items = [values]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, (list, tuple, set)):
            for nested in _normalize_list(list(item)):
                if nested not in seen:
                    seen.add(nested)
                    normalized.append(nested)
            continue
        candidate = _normalize_value(_unwrap_value(item))
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def _extract_requested_facets(request_parameters: dict) -> list[str]:
    facets: list[str] = []
    cloud_resource_facets = request_parameters.get("cloud_resource_facets")
    if isinstance(cloud_resource_facets, dict):
        for key, raw_values in cloud_resource_facets.items():
            facet_key = _normalize_value(key)
            if not facet_key:
                continue
            raw_list = raw_values if isinstance(raw_values, list) else [raw_values]
            for raw_value in raw_list:
                facet_value = _normalize_value(raw_value)
                if not facet_value:
                    continue
                facets.append(f"{facet_key}:{facet_value}")
    return _normalize_list(facets)


def _extract_compute_context(payload: dict) -> dict:
    request_payload = payload.get("catalogServiceRequest")
    if not isinstance(request_payload, dict):
        request_payload = {}
    request_parameters = request_payload.get("requestParameters")
    if not isinstance(request_parameters, dict):
        request_parameters = {}

    compute: dict = {}
    ext_params = request_parameters.get("extensibleParameters")
    if isinstance(ext_params, list):
        for item in ext_params:
            if not isinstance(item, dict):
                continue
            candidate = item.get("Compute")
            if isinstance(candidate, dict):
                compute = candidate
                break

    resource_bundle_config = compute.get("resource_bundle_config")
    if not isinstance(resource_bundle_config, dict):
        resource_bundle_config = {}

    system_disk_config = _unwrap_value(compute.get("system_disk_config"))
    if not isinstance(system_disk_config, dict):
        system_disk_config = {}

    requested_facets = _extract_requested_facets(request_parameters)
    requested_facets.extend(_normalize_list(_unwrap_value(compute.get("tags"))))
    requested_facets.extend(_normalize_list(_unwrap_value(compute.get("tags_copy"))))
    requested_facets = _normalize_list(requested_facets)

    return {
        "requested_facets": requested_facets,
        "resource_bundle_id": _normalize_value(_unwrap_value(resource_bundle_config.get("policy_resource"))),
        "resource_bundle_policy": _normalize_value(_unwrap_value(resource_bundle_config.get("policy_type"))),
        "compute_profile_id": _normalize_value(_unwrap_value(compute.get("compute_profile_id"))),
        "flavor_id": _normalize_value(_unwrap_value(compute.get("flavor_id"))),
        "logic_template_id": _normalize_value(_unwrap_value(compute.get("logic_template_id"))),
        "template_id": _normalize_value(_unwrap_value(compute.get("template_id"))),
        "network_id": _normalize_value(_unwrap_value(compute.get("network_id") or compute.get("networkId"))),
        "cpu": _normalize_value(_unwrap_value(compute.get("cpus") or compute.get("cpu"))),
        "memory": _normalize_value(_unwrap_value(compute.get("memory"))),
        "system_disk_size": _normalize_value(system_disk_config.get("size")),
        "credential_user": _normalize_value((compute.get("credential") or {}).get("user")),
    }


def _looks_failed_state(state: object) -> bool:
    normalized = _normalize_value(state).upper().replace("-", "_")
    if not normalized:
        return False
    if normalized in {"FAILED", "INITIALING_FAILED", "CANCELLED", "CANCELED", "REJECTED"}:
        return True
    return "FAIL" in normalized or "ERROR" in normalized


def _looks_failed_provision_state(state: object) -> bool:
    normalized = _normalize_value(state).lower()
    if not normalized:
        return False
    return "fail" in normalized or "error" in normalized


def _is_submission_confirmed(snapshot: dict) -> bool:
    if not snapshot.get("ok"):
        return False
    state = _normalize_value(snapshot.get("state")).upper().replace("-", "_")
    if not state:
        return False
    if _looks_failed_state(state) or _looks_failed_provision_state(snapshot.get("provision_state")):
        return False
    if _normalize_value(snapshot.get("process_instance_id")):
        return True
    return state not in {"INITIALING", "INITIALIZING"}


def _verification_wait_seconds(attempt: int) -> float:
    """Use a fixed linear backoff: step, 2*step, 3*step, ..."""
    return _VERIFY_INTERVAL_SECONDS * max(1, int(attempt) + 1)


def _extract_request_records(result: object) -> list[dict]:
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        return [result]
    return []


def _extract_ticket_id(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""

    for key in ("workflowId", "workflow_id", "ticketId", "ticket_id"):
        candidate = _normalize_value(payload.get(key))
        if candidate:
            return candidate

    current_activity = payload.get("currentActivity")
    if isinstance(current_activity, dict):
        for key in ("workflowId", "workflow_id", "ticketId", "ticket_id"):
            candidate = _normalize_value(current_activity.get(key))
            if candidate:
                return candidate

    return ""


def _resolve_display_request_id(ticket_id: str) -> str:
    return ticket_id


def _fetch_request_snapshot(request_id: str) -> dict:
    try:
        resp = requests.get(
            f"{BASE_URL}/generic-request/{request_id}",
            headers=create_headers(AUTH_TOKEN),
            verify=False,
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        return {
            "ok": False,
            "request_id": request_id,
            "message": str(exc),
        }

    if resp.status_code != 200:
        return {
            "ok": False,
            "request_id": request_id,
            "status_code": resp.status_code,
            "message": (resp.text or "").strip(),
        }

    try:
        payload = resp.json()
    except json.JSONDecodeError:
        return {
            "ok": False,
            "request_id": request_id,
            "status_code": resp.status_code,
            "message": f"Invalid verification response: {resp.text}",
        }

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "request_id": request_id,
            "status_code": resp.status_code,
            "message": f"Unexpected verification payload: {payload}",
        }

    return {
        "ok": True,
        "request_id": _normalize_value(payload.get("id")) or request_id,
        "workflow_id": _extract_ticket_id(payload),
        "state": _normalize_value(payload.get("state")),
        "provision_state": _normalize_value(payload.get("provisionState")),
        "error": _normalize_value(payload.get("errMsg") or payload.get("errorMessage")),
        "process_instance_id": _normalize_value(payload.get("processInstanceId")),
        "catalog_id": _normalize_value(payload.get("catalogId")),
        "catalog_name": _normalize_value(payload.get("catalogName")),
        "request_name": _normalize_value(payload.get("name")),
        "business_group_id": _normalize_value(payload.get("businessGroupId")),
        "compute_context": _extract_compute_context(payload),
    }


def _fetch_business_group_context(business_group_id: str) -> dict:
    if not business_group_id:
        return {}
    try:
        resp = requests.get(
            f"{BASE_URL}/business-groups/{business_group_id}",
            headers=create_headers(AUTH_TOKEN),
            verify=False,
            timeout=30,
        )
    except requests.exceptions.RequestException:
        return {}
    if resp.status_code != 200:
        return {}
    try:
        payload = resp.json()
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "id": _normalize_value(payload.get("id")) or business_group_id,
        "name": _normalize_value(payload.get("name") or payload.get("nameZh")),
        "code": _normalize_value(payload.get("code")),
    }


def _fetch_resource_bundle_context(resource_bundle_id: str) -> dict:
    if not resource_bundle_id:
        return {}
    try:
        resp = requests.get(
            f"{BASE_URL}/resource-bundles/{resource_bundle_id}",
            headers=create_headers(AUTH_TOKEN),
            verify=False,
            timeout=30,
        )
    except requests.exceptions.RequestException:
        return {}
    if resp.status_code != 200:
        return {}
    try:
        payload = resp.json()
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "id": _normalize_value(payload.get("id")) or resource_bundle_id,
        "name": _normalize_value(payload.get("name")),
        "facets": _normalize_list(payload.get("facets")),
        "cloud_entry_type_id": _normalize_value(payload.get("cloudEntryTypeId")),
        "enabled": bool(payload.get("enabled", False)),
        "global": bool(payload.get("global", False)),
    }


def _build_failure_diagnostics(verified: dict) -> list[str]:
    diagnostics: list[str] = []
    catalog_name = _normalize_value(verified.get("catalog_name"))
    request_name = _normalize_value(verified.get("request_name"))
    if catalog_name:
        diagnostics.append(f"Catalog: {catalog_name}")
    if request_name:
        diagnostics.append(f"Request Name: {request_name}")

    business_group_id = _normalize_value(verified.get("business_group_id"))
    business_group = _fetch_business_group_context(business_group_id)
    business_group_name = _normalize_value(business_group.get("name"))
    if business_group_name or business_group_id:
        bg_display = business_group_name or business_group_id
        if business_group_name and business_group_id:
            bg_display = f"{business_group_name} ({business_group_id})"
        diagnostics.append(f"Business Group: {bg_display}")

    compute_context = verified.get("compute_context")
    if not isinstance(compute_context, dict):
        compute_context = {}

    requested_facets = _normalize_list(compute_context.get("requested_facets"))
    if requested_facets:
        diagnostics.append(f"Requested Facets: {', '.join(requested_facets)}")

    resource_bundle_id = _normalize_value(compute_context.get("resource_bundle_id"))
    resource_bundle = _fetch_resource_bundle_context(resource_bundle_id)
    resource_bundle_name = _normalize_value(resource_bundle.get("name"))
    if resource_bundle_name or resource_bundle_id:
        rb_display = resource_bundle_name or resource_bundle_id
        if resource_bundle_name and resource_bundle_id:
            rb_display = f"{resource_bundle_name} ({resource_bundle_id})"
        diagnostics.append(f"Selected Resource Bundle: {rb_display}")
    resource_bundle_facets = _normalize_list(resource_bundle.get("facets"))
    if resource_bundle_facets:
        diagnostics.append(f"Resource Bundle Facets: {', '.join(resource_bundle_facets)}")

    resource_bundle_policy = _normalize_value(compute_context.get("resource_bundle_policy"))
    if resource_bundle_policy:
        diagnostics.append(f"Resource Bundle Policy: {resource_bundle_policy}")

    for label, key in (
        ("Compute Profile ID", "compute_profile_id"),
        ("Flavor ID", "flavor_id"),
        ("Template ID", "template_id"),
        ("Logic Template ID", "logic_template_id"),
        ("Network ID", "network_id"),
    ):
        value = _normalize_value(compute_context.get(key))
        if value:
            diagnostics.append(f"{label}: {value}")

    cpu_value = _normalize_value(compute_context.get("cpu"))
    memory_value = _normalize_value(compute_context.get("memory"))
    if cpu_value or memory_value:
        cpu_memory = []
        if cpu_value:
            cpu_memory.append(f"CPU={cpu_value}")
        if memory_value:
            cpu_memory.append(f"Memory={memory_value}")
        diagnostics.append(f"Requested Shape: {', '.join(cpu_memory)}")

    system_disk_size = _normalize_value(compute_context.get("system_disk_size"))
    if system_disk_size:
        diagnostics.append(f"System Disk Size: {system_disk_size}")

    credential_user = _normalize_value(compute_context.get("credential_user"))
    if credential_user:
        diagnostics.append(f"Credential User: {credential_user}")

    return diagnostics


def _verify_submitted_request(request_id: str) -> dict:
    last_snapshot = {
        "ok": False,
        "request_id": request_id,
        "message": "Verification did not return any response.",
    }

    for attempt in range(_VERIFY_ATTEMPTS):
        snapshot = _fetch_request_snapshot(request_id)
        last_snapshot = snapshot

        if snapshot.get("ok"):
            state = snapshot.get("state")
            provision_state = snapshot.get("provision_state")
            if _looks_failed_state(state) or _looks_failed_provision_state(provision_state):
                snapshot["failed"] = True
                return snapshot

        if attempt < _VERIFY_ATTEMPTS - 1:
            time.sleep(_verification_wait_seconds(attempt))

    last_snapshot["failed"] = bool(
        last_snapshot.get("ok")
        and (
            _looks_failed_state(last_snapshot.get("state"))
            or _looks_failed_provision_state(last_snapshot.get("provision_state"))
        )
    )
    return last_snapshot


def _load_runtime_cookies() -> dict:
    raw = os.environ.get("ATLASCLAW_COOKIES", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _fetch_current_user() -> dict:
    """Fetch current user info from CMP API. Returns dict with userId/userLoginId or empty dict."""
    try:
        url = f"{BASE_URL}/users/current-user-details"
        headers = create_headers(AUTH_TOKEN)
        resp = requests.get(url, headers=headers, verify=False, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "userId": str(data.get("id", "") or "").strip(),
                "userLoginId": str(data.get("loginId", "") or data.get("userLoginId", "") or data.get("username", "") or "").strip(),
            }
    except Exception:
        pass
    return {}


def _enrich_request_body(body: object) -> object:
    if not isinstance(body, dict):
        return body

    enriched = dict(body)

    # Remove null/None values for userId and userLoginId so they can be filled
    if enriched.get("userId") is None:
        enriched.pop("userId", None)
    if enriched.get("userLoginId") is None:
        enriched.pop("userLoginId", None)

    if enriched.get("userId") and enriched.get("userLoginId"):
        return enriched

    # Source 1: ATLASCLAW_COOKIES
    cookies = _load_runtime_cookies()
    cookie_user_id = str(cookies.get("userId", "") or "").strip()
    if cookie_user_id and not enriched.get("userId"):
        enriched["userId"] = cookie_user_id

    cookie_login_id = str(cookies.get("userLoginId", "") or "").strip()
    if cookie_login_id and not enriched.get("userLoginId"):
        enriched["userLoginId"] = cookie_login_id

    # Source 2: ATLASCLAW_USER_ID env var
    runtime_user_id = str(os.environ.get("ATLASCLAW_USER_ID", "") or "").strip()
    if runtime_user_id and not enriched.get("userLoginId"):
        enriched["userLoginId"] = runtime_user_id

    # Source 3: CMP API /users/current (final fallback)
    if not enriched.get("userLoginId") or not enriched.get("userId"):
        api_user = _fetch_current_user()
        if api_user.get("userId") and not enriched.get("userId"):
            enriched["userId"] = api_user["userId"]
        if api_user.get("userLoginId") and not enriched.get("userLoginId"):
            enriched["userLoginId"] = api_user["userLoginId"]

    return enriched

# -- Parse arguments -----------------------------------------------------------
parser = argparse.ArgumentParser(description='Submit request to SmartCMP')
group = parser.add_mutually_exclusive_group(required=False)
group.add_argument('--file', '-f', help='Path to JSON file containing request body')
group.add_argument('--json', '-j', '--json-body', help='JSON string (avoid in PowerShell)')
args = parser.parse_args()

if not args.file and not args.json:
    print("ERROR: No request body provided.")
    print("You must pass the json_body parameter with the complete request JSON.")
    print('For cloud resources: {"catalogId":"...","catalogName":"Linux VM","userLoginId":"admin","<businessGroup key>":"<defaultValue>","name":"vm-01","resourceSpecs":[{"node":"Compute","type":"cloudchef.nodes.Compute","computeProfileName":"2c4g"}]}')
    print('For tickets: {"catalogId":"...","catalogName":"ticket","userLoginId":"admin","<businessGroup key>":"<defaultValue>","name":"ticket-title","genericRequest":{"description":"problem description"}}')
    print("FORBIDDEN fields: Do NOT add priority, category, requestor, parameters, impactScope, urgency, contactName, or any field not shown above.")
    print("First show the user a JSON preview, get their confirmation, then call this tool with the json_body parameter set to the confirmed JSON string.")
    sys.exit(0)

# -- Load request body ---------------------------------------------------------
def _sanitize_json_string(s: str) -> str:
    """Replace smart/curly quotes with standard ASCII quotes."""
    return (s
        .replace('\u201c', '"')   # left double curly quote
        .replace('\u201d', '"')   # right double curly quote
        .replace('\u2018', "'")   # left single curly quote
        .replace('\u2019', "'")   # right single curly quote
        .replace('\uff02', '"')   # fullwidth quotation mark
    )

try:
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            body = json.load(f)
    else:
        raw_json = _sanitize_json_string(args.json)
        body = json.loads(raw_json)
except json.JSONDecodeError as e:
    print(f"[ERROR] Invalid JSON: {e}")
    sys.exit(1)
except FileNotFoundError:
    print(f"[ERROR] File not found: {args.file}")
    sys.exit(1)

body = _enrich_request_body(body)

# -- Normalize resourceSpecs to array -----------------------------------------
# SmartCMP backend expects resourceSpecs as an array (ArrayList<ResourceSpec>).
# LLMs sometimes send it as a single object; wrap it defensively.
if isinstance(body, dict) and "resourceSpecs" in body:
    specs = body["resourceSpecs"]
    if isinstance(specs, dict):
        body["resourceSpecs"] = [specs]

# -- Submit request ------------------------------------------------------------
url = f"{BASE_URL}/generic-request/submit"
headers = create_headers(AUTH_TOKEN)

try:
    resp = requests.post(url, headers=headers, json=body, verify=False, timeout=30)
    result = resp.json()
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Request failed: {e}")
    sys.exit(1)
except json.JSONDecodeError:
    print(f"[ERROR] Invalid response: {resp.text}")
    sys.exit(1)

# -- Output result -------------------------------------------------------------
catalog_name = body.get("catalogName", "")
request_name = body.get("name", "")

if resp.status_code != 200:
    print(f"[FAILED] HTTP {resp.status_code}")
    if isinstance(result, dict):
        print(f"  Message: {result.get('message', result.get('error', json.dumps(result, ensure_ascii=False)))}")
    else:
        print(f"  Response: {result}")
    sys.exit(1)

records = _extract_request_records(result)
if not records:
    print("[FAILED] Submission failed")
    print("  Message: SmartCMP returned HTTP 200 but no request record.")
    print(f"  Response: {result}")
    sys.exit(1)

overall_failed = False

for index, record in enumerate(records):
    if index > 0:
        print("  ---")

    req_id = _normalize_value(record.get("id"))
    ticket_id = _extract_ticket_id(record)
    display_request_id = _resolve_display_request_id(ticket_id)
    submit_state = _normalize_value(record.get("state"))
    submit_error = _normalize_value(record.get("errorMessage"))

    if submit_error:
        overall_failed = True
        print("[FAILED] Submission failed")
        if display_request_id:
            print(f"  Request ID: {display_request_id}")
        if submit_state:
            print(f"  State: {submit_state}")
        print(f"  Error: {submit_error}")
        continue

    if not req_id or req_id.lower() in {"n/a", "none", "null"}:
        overall_failed = True
        print("[FAILED] Submission failed")
        if display_request_id:
            print(f"  Request ID: {display_request_id}")
        print("  Message: SmartCMP returned HTTP 200 but no Request ID.")
        continue

    verified = _verify_submitted_request(req_id)
    ticket_id = _normalize_value(verified.get("workflow_id")) or ticket_id
    display_request_id = _resolve_display_request_id(ticket_id)
    verified_state = _normalize_value(verified.get("state")) or submit_state or "N/A"
    provision_state = _normalize_value(verified.get("provision_state"))
    verified_error = _normalize_value(verified.get("error"))

    if not verified.get("ok"):
        # The submit endpoint already returned a concrete Request ID, so treat
        # verification gaps as pending rather than a hard failure to avoid
        # encouraging duplicate submissions.
        print("[PENDING] Request submitted, but not yet verifiable in SmartCMP")
        print(f"  Request ID: {display_request_id}")
        if submit_state:
            print(f"  Submit State: {submit_state}")
        if verified.get("status_code") is not None:
            print(f"  Verify HTTP: {verified.get('status_code')}")
        if verified.get("message"):
            print(f"  Message: {verified.get('message')}")
        print("  Note: Track this request by Request ID instead of resubmitting it.")
        continue

    if verified.get("failed"):
        overall_failed = True
        print("[FAILED] Request was created but initialization failed")
        print(f"  Request ID: {display_request_id}")
        print(f"  State: {verified_state}")
        if provision_state:
            print(f"  Provision State: {provision_state}")
        if verified_error:
            print(f"  Error: {verified_error}")
        diagnostics = _build_failure_diagnostics(verified)
        if diagnostics:
            print("  Diagnosis:")
            for entry in diagnostics:
                print(f"    - {entry}")
        continue

    if not _is_submission_confirmed(verified):
        print("[PENDING] Request submitted, but workflow has not been confirmed yet")
        print(f"  Request ID: {display_request_id}")
        print(f"  State: {verified_state}")
        if provision_state:
            print(f"  Provision State: {provision_state}")
        print(
            f"  Message: SmartCMP did not expose a confirmed workflow within {_VERIFY_ATTEMPTS} checks."
        )
        print("  Note: Track this request by Request ID instead of resubmitting it.")
        continue

    print("[SUCCESS] Request submitted")
    print(f"  Request ID: {display_request_id}")
    print(f"  State: {verified_state}")
    if provision_state:
        print(f"  Provision State: {provision_state}")
    if catalog_name:
        print(f"  Catalog: {catalog_name}")
    if request_name:
        print(f"  Name: {request_name}")

sys.exit(1 if overall_failed else 0)
