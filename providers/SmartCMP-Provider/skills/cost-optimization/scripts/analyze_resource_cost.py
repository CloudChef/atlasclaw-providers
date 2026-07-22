#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Collect SmartCMP resource cost evidence for outer-LLM analysis."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPT_DIR = SCRIPT_DIR.parent.parent / "shared" / "scripts"
DATASOURCE_SCRIPT_DIR = SCRIPT_DIR.parent.parent / "datasource" / "scripts"
for import_root in (SCRIPT_DIR, SHARED_SCRIPT_DIR):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from _common import (  # noqa: E402
    build_object_open_action,
    build_resource_page_href,
    infer_resource_page_category,
    request_timeout,
    require_config,
)
from _cost_common import extract_list_payload  # noqa: E402
from _resource_cost_analysis import (  # noqa: E402
    build_analysis_payload,
    build_policy_coverages,
    build_resource_projection,
    project_execution_extra,
    project_violation,
    render_output,
)


RESOURCE_SEARCH_SIZE = 100
RESOURCE_SEARCH_MAX_PAGES = 1_000
API_PAGE_SIZE = 100
API_MAX_PAGES = 1_000


class ResourceResolutionError(ValueError):
    """Raised when a user-visible SmartCMP resource cannot be resolved uniquely."""


def fetch_currency_evidence(
    base_url: str,
    headers: dict[str, str],
) -> tuple[str | None, str, str, str | None]:
    """Read verified SmartCMP tenant currency metadata without a guessed fallback.

    Args:
        base_url: SmartCMP platform API base URL.
        headers: Current-user SmartCMP headers.

    Returns:
        Symbol, currency code, evidence source, and a generic error when unavailable.
    """
    try:
        setting_response = requests.get(
            f"{base_url}/tenants/current/setting",
            headers=headers,
            verify=False,
            timeout=request_timeout(),
        )
        setting_response.raise_for_status()
        setting_payload = setting_response.json()
        currency_code = (
            str(setting_payload.get("currencyUnitType") or "").strip()
            if isinstance(setting_payload, Mapping)
            else ""
        )
        if not currency_code:
            raise ValueError("currency code is unavailable")

        units_response = requests.get(
            f"{base_url}/tenants/currencyUnits",
            headers=headers,
            verify=False,
            timeout=request_timeout(),
        )
        units_response.raise_for_status()
        units_payload = units_response.json()
        if not isinstance(units_payload, list):
            raise ValueError("currency units are unavailable")
        for unit in units_payload:
            if not isinstance(unit, Mapping) or str(unit.get("code") or "") != currency_code:
                continue
            symbol = str(unit.get("symbol") or "").strip()
            if symbol:
                return symbol, currency_code, "smartcmp_tenant_settings", None
        raise ValueError("currency symbol is unavailable")
    except (requests.RequestException, TypeError, ValueError):
        return None, "", "", "SmartCMP tenant currency evidence is unavailable."


def _load_module_from_path(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load module from path: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resource_module = _load_module_from_path(
    "cost_optimization_resource_list_resource_local",
    DATASOURCE_SCRIPT_DIR / "list_resource.py",
)
load_resource_records = resource_module.load_resource_records
resource_request_json = resource_module.request_json


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse one resource-first cost analysis request.

    Args:
        argv: Optional command-line arguments for tests and embedded callers.

    Returns:
        Parsed resource name, list metadata, and compatibility ID inputs.
    """
    parser = argparse.ArgumentParser(
        description="Collect SmartCMP resource cost evidence for LLM analysis."
    )
    parser.add_argument("--resource-name", default="", help="Exact visible SmartCMP resource name.")
    parser.add_argument("--resource-index", type=int, help="Visible index from the latest resource list.")
    parser.add_argument("--resource-directory-json", default="", help="Hidden latest resource-list metadata.")
    parser.add_argument("--resource-id", default="", help="Internal compatibility-only SmartCMP resource ID.")
    return parser.parse_args(argv)


def _extract_directory_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("resources", "items", "metadata", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    recent_metadata = payload.get("recent_tool_metadata")
    if isinstance(recent_metadata, list):
        for entry in reversed(recent_metadata):
            if not isinstance(entry, dict):
                continue
            if entry.get("tool_name") == "smartcmp_list_all_resource" and isinstance(entry.get("metadata"), list):
                return [item for item in entry["metadata"] if isinstance(item, dict)]
    return []


def parse_resource_directory(raw_value: Any) -> list[dict[str, Any]]:
    """Parse resource-list metadata emitted by ``smartcmp_list_all_resource``.

    Args:
        raw_value: Direct metadata, JSON text, or Current Workflow Context.

    Returns:
        Resource directory items that contain an internal target ID.

    Raises:
        ResourceResolutionError: If supplied metadata is not valid JSON.
    """
    if raw_value in (None, ""):
        return []
    payload = raw_value
    if isinstance(raw_value, str):
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ResourceResolutionError("Resource list metadata is not valid JSON.") from exc
    return [
        item
        for item in _extract_directory_items(payload)
        if str(item.get("id") or item.get("object_id") or item.get("resourceId") or "").strip()
    ]


def _directory_id(item: Mapping[str, Any]) -> str:
    return str(item.get("id") or item.get("object_id") or item.get("resourceId") or "").strip()


def _directory_name(item: Mapping[str, Any]) -> str:
    return str(item.get("name") or item.get("object_name") or item.get("displayName") or "").strip()


def _directory_index(item: Mapping[str, Any]) -> int | None:
    try:
        return int(item.get("index"))
    except (TypeError, ValueError):
        return None


def _extract_total_pages(payload: Any) -> int | None:
    if not isinstance(payload, Mapping):
        return None
    value = payload.get("totalPages")
    try:
        return max(int(value), 0) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _search_resource_by_name(
    resource_name: str,
    *,
    base_url: str,
    headers: dict[str, str],
) -> tuple[str, str]:
    normalized_name = resource_name.strip()
    matches: list[dict[str, Any]] = []
    for page in range(1, RESOURCE_SEARCH_MAX_PAGES + 1):
        response = requests.get(
            f"{base_url}/nodes/search",
            headers=headers,
            params={
                "page": page,
                "size": RESOURCE_SEARCH_SIZE,
                "queryValue": normalized_name,
                "sort": "createdDate,desc",
                "relation": "AND",
                "fullMatch": "false",
                "category": "-1",
            },
            verify=False,
            timeout=request_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
        page_items = extract_list_payload(payload)
        matches.extend(
            item
            for item in page_items
            if isinstance(item, dict)
            and str(item.get("name") or "").strip().casefold() == normalized_name.casefold()
            and str(item.get("id") or "").strip()
        )
        total_pages = _extract_total_pages(payload)
        if isinstance(payload, dict) and payload.get("last") is True:
            break
        if total_pages is not None and page >= total_pages:
            break
        if total_pages is None and len(page_items) < RESOURCE_SEARCH_SIZE:
            break
    else:
        raise ResourceResolutionError(
            f"Resource search exceeded {RESOURCE_SEARCH_MAX_PAGES} pages for name '{normalized_name}'."
        )

    unique_matches = {str(item.get("id")): item for item in matches}
    if not unique_matches:
        raise ResourceResolutionError(f"No SmartCMP resource exactly matched name '{normalized_name}'.")
    if len(unique_matches) > 1:
        raise ResourceResolutionError(
            f"Multiple SmartCMP resources exactly matched name '{normalized_name}'. "
            "List resources and choose a table #."
        )
    selected = next(iter(unique_matches.values()))
    return str(selected.get("id") or ""), str(selected.get("name") or normalized_name)


def resolve_resource_target(
    *,
    resource_id: str,
    resource_name: str,
    resource_index: int | None,
    directory_items: list[dict[str, Any]],
    base_url: str,
    headers: dict[str, str],
) -> tuple[str, str]:
    """Resolve one name-first resource target into an internal SmartCMP ID.

    Args:
        resource_id: Compatibility-only internal target.
        resource_name: Exact user-visible resource name.
        resource_index: Visible table index from recent list metadata.
        directory_items: Parsed recent resource-list metadata.
        base_url: SmartCMP platform API base URL.
        headers: Current-user SmartCMP headers.

    Returns:
        Internal resource ID and visible resource name.

    Raises:
        ResourceResolutionError: If the target is missing, ambiguous, or inconsistent.
    """
    normalized_id = str(resource_id or "").strip()
    normalized_name = str(resource_name or "").strip()
    if resource_index is not None:
        if resource_index <= 0:
            raise ResourceResolutionError("Resource index must be a positive integer.")
        matches = [item for item in directory_items if _directory_index(item) == resource_index]
        if len(matches) != 1:
            raise ResourceResolutionError(
                f"No unique resource is available at index {resource_index}. List resources again first."
            )
        selected_id = _directory_id(matches[0])
        selected_name = _directory_name(matches[0])
        if normalized_name and selected_name.casefold() != normalized_name.casefold():
            raise ResourceResolutionError(
                f"Resource index {resource_index} is '{selected_name}', not '{normalized_name}'."
            )
        if normalized_id and selected_id != normalized_id:
            raise ResourceResolutionError("Resource index does not match the provided internal target.")
        return selected_id, selected_name or normalized_name

    if normalized_name and directory_items:
        matches = [
            item for item in directory_items if _directory_name(item).casefold() == normalized_name.casefold()
        ]
        if len(matches) == 1:
            selected_id = _directory_id(matches[0])
            if normalized_id and selected_id != normalized_id:
                raise ResourceResolutionError("Resource name does not match the provided internal target.")
            return selected_id, _directory_name(matches[0])
        if len(matches) > 1:
            raise ResourceResolutionError(
                f"Multiple listed resources exactly matched name '{normalized_name}'. Choose one by table #."
            )

    if normalized_name:
        selected_id, selected_name = _search_resource_by_name(
            normalized_name,
            base_url=base_url,
            headers=headers,
        )
        if normalized_id and selected_id != normalized_id:
            raise ResourceResolutionError(
                "Resource name does not match the provided internal target."
            )
        return selected_id, selected_name
    if normalized_id:
        return normalized_id, ""
    raise ResourceResolutionError(
        "Provide an exact resource name or select one from the latest resource table."
    )


def _fetch_paginated(
    url: str,
    *,
    headers: dict[str, str],
    params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for page in range(API_MAX_PAGES):
        request_params = dict(params or {})
        request_params.update({"page": page, "size": API_PAGE_SIZE})
        response = requests.get(
            url,
            headers=headers,
            params=request_params,
            verify=False,
            timeout=request_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
        page_items = [item for item in extract_list_payload(payload) if isinstance(item, dict)]
        items.extend(page_items)
        total_pages = _extract_total_pages(payload)
        if isinstance(payload, dict) and payload.get("last") is True:
            break
        if total_pages is not None and page + 1 >= total_pages:
            break
        if total_pages is None and len(page_items) < API_PAGE_SIZE:
            break
    else:
        raise RuntimeError(f"SmartCMP pagination exceeded {API_MAX_PAGES} pages for {url}.")
    return items


def fetch_cost_policies(base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Read all SmartCMP cost optimization policies.

    Args:
        base_url: SmartCMP platform API base URL.
        headers: Current-user SmartCMP headers.

    Returns:
        All policy records in the COST-OPTIMIZATION category tree.
    """
    return _fetch_paginated(
        f"{base_url}/compliance-policies/search",
        headers=headers,
        params={"category": "COST-OPTIMIZATION"},
    )


def fetch_active_violations(
    *,
    base_url: str,
    headers: dict[str, str],
    resource_id: str,
) -> list[dict[str, Any]]:
    """Read active cost violations and retain exact resource matches.

    Args:
        base_url: SmartCMP platform API base URL.
        headers: Current-user SmartCMP headers.
        resource_id: Selected internal resource ID.

    Returns:
        Active violation records whose resource ID exactly matches the selected resource.
    """
    violations = _fetch_paginated(
        f"{base_url}/compliance-policies/violations/search",
        headers=headers,
        params={
            "status": "ACTIVED",
            "category": "COST-OPTIMIZATION",
            "resourceId": resource_id,
            "sort": "lastExecuteDate,desc",
        },
    )
    return [
        violation for violation in violations if str(violation.get("resourceId") or "") == resource_id
    ]


def _project_resource_execution(execution: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "executionId": str(execution.get("executionId") or execution.get("taskInstanceId") or ""),
        "policyId": str(execution.get("policyId") or ""),
        "status": str(execution.get("status") or ""),
        "startTime": execution.get("startTime"),
        "endTime": execution.get("endTime"),
        "policyViolationId": str(execution.get("policyViolationId") or ""),
        "errorReported": bool(str(execution.get("errMsg") or "").strip()),
        "extra": project_execution_extra(execution.get("extra")),
    }


def enrich_resource_executions(
    policy_coverages: list[dict[str, Any]],
    *,
    base_url: str,
    headers: dict[str, str],
    resource_id: str,
) -> list[str]:
    """Attach latest exact resource executions to applicable policy coverages.

    Args:
        policy_coverages: Mutable policy coverage records.
        base_url: SmartCMP platform API base URL.
        headers: Current-user SmartCMP headers.
        resource_id: Selected internal resource ID.

    Returns:
        Best-effort execution lookup errors; failed lookups are also attached as failed executions.
    """
    errors: list[str] = []
    execution_cache: dict[str, list[dict[str, Any]] | Exception] = {}
    for coverage in policy_coverages:
        if coverage.get("applicable") is not True:
            continue
        execution_id = str(coverage.get("lastExecutionId") or "")
        if not execution_id:
            last_status = str(coverage.get("lastExecuteStatus") or "").upper()
            if last_status in {"ERROR", "FAILED", "FAILURE"}:
                coverage["resourceExecution"] = {"status": last_status, "extra": {}}
            continue
        if execution_id not in execution_cache:
            try:
                execution_cache[execution_id] = _fetch_paginated(
                    f"{base_url}/compliance-policies/resource-executions/search",
                    headers=headers,
                    params={"executionId": execution_id},
                )
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                execution_cache[execution_id] = exc
        cached = execution_cache[execution_id]
        if isinstance(cached, Exception):
            message = f"Resource execution lookup failed for policy '{coverage.get('policyName')}'."
            errors.append(message)
            coverage["resourceExecution"] = {"status": "ERROR", "errMsg": message, "extra": {}}
            continue
        matching = [
            execution
            for execution in cached
            if str(execution.get("executionId") or execution.get("taskInstanceId") or "")
            == execution_id
            and str(execution.get("resourceId") or "") == resource_id
            and str(execution.get("policyId") or "") == str(coverage.get("policyId") or "")
        ]
        if matching:
            coverage["resourceExecution"] = _project_resource_execution(matching[0])
    return errors


def _build_resource_actions(
    base_url: str,
    resource_id: str,
    resource: Mapping[str, Any],
) -> list[dict[str, Any]]:
    resource_types = {
        str(resource.get("componentType") or ""),
        str(resource.get("resourceType") or ""),
    }
    category = infer_resource_page_category(dict(resource))
    if not category and any(
        value == "resource.iaas.machine" or value.startswith("resource.iaas.machine.")
        for value in resource_types
    ):
        category = "virtual-machines"
    if not category:
        category = "cloud-resource"
    href = build_resource_page_href(base_url, resource_id, category=category)
    action = build_object_open_action(
        href,
        action_id="open_resource",
        label_en="Open resource",
        label_zh="打开资源",
    )
    return [action] if action else []


def main(argv: list[str] | None = None) -> int:
    """Resolve one resource and emit read-only cost evidence for LLM analysis.

    Args:
        argv: Optional command-line arguments for tests and embedded callers.

    Returns:
        Process exit code: zero on successful evidence collection, one on failure.
    """
    args = parse_args(argv)
    try:
        base_url, _auth_token, headers, _instance = require_config()
        directory_items = parse_resource_directory(args.resource_directory_json)
        resource_id, requested_name = resolve_resource_target(
            resource_id=args.resource_id,
            resource_name=args.resource_name,
            resource_index=args.resource_index,
            directory_items=directory_items,
            base_url=base_url,
            headers=headers,
        )
        records = load_resource_records(
            [resource_id],
            base_url=base_url,
            headers=headers,
            request_fn=resource_request_json,
        )
        if not records or records[0].get("fetchStatus") != "ok":
            raise RuntimeError(f"Resource '{requested_name or 'selected resource'}' could not be loaded.")

        record = records[0]
        resource = build_resource_projection(record)
        resolved_name = str(resource.get("name") or "").strip()
        if (
            requested_name
            and resolved_name
            and resolved_name != "unknown resource"
            and resolved_name.casefold() != requested_name.casefold()
        ):
            raise ResourceResolutionError(
                f"Resolved resource is '{resolved_name}', not '{requested_name}'."
            )
        if requested_name and resource.get("name") == "unknown resource":
            resource["name"] = requested_name
        policies = fetch_cost_policies(base_url, headers)
        policy_coverages = build_policy_coverages(
            policies,
            resource=resource,
            resource_id=resource_id,
        )
        violations = [
            project_violation(violation)
            for violation in fetch_active_violations(
                base_url=base_url,
                headers=headers,
                resource_id=resource_id,
            )
        ]
        for coverage in policy_coverages:
            coverage["activeViolationIds"] = [
                violation["violationId"]
                for violation in violations
                if violation.get("policyId") == coverage.get("policyId")
            ]
        errors = enrich_resource_executions(
            policy_coverages,
            base_url=base_url,
            headers=headers,
            resource_id=resource_id,
        )
        if record.get("errors"):
            errors.append("Datasource resource lookup reported fallback or enrichment errors.")
        currency, currency_code, currency_source, currency_error = fetch_currency_evidence(
            base_url,
            headers,
        )
        if currency_error:
            errors.append(currency_error)
        payload = build_analysis_payload(
            resource_id=resource_id,
            resource=resource,
            policy_coverages=policy_coverages,
            active_violations=violations,
            currency=currency,
            currency_code=currency_code,
            currency_source=currency_source,
            errors=errors,
            object_actions=_build_resource_actions(base_url, resource_id, resource),
        )
    except (ResourceResolutionError, RuntimeError, requests.RequestException, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(render_output(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
