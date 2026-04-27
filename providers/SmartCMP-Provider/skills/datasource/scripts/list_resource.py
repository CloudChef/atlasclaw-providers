#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP resource details by resource ID."""

import argparse
import json
import sys

import requests
from requests import RequestException

try:
    from _common import require_config
except ImportError:
    import os

    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import require_config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="List SmartCMP resource details by resource ID, or list all resources if no IDs provided."
    )
    parser.add_argument("resource_ids", nargs="*", help="Resource IDs to query. If not provided, list all resources.")
    parser.add_argument("--page", "-p", type=int, default=1, help="Page number for listing all resources (default: 1)")
    parser.add_argument("--size", "-s", type=int, default=50, help="Page size for listing all resources (default: 50)")
    return parser.parse_args(argv)


def request_json(method, path, *, base_url, headers, payload=None, params=None):
    response = requests.request(
        method,
        f"{base_url}{path}",
        headers=headers,
        json=payload,
        params=params,
        verify=False,
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("Response did not contain valid JSON.") from exc


def extract_list_payload(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("content", "items", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("content", "items", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


def normalize_resource_summary(item):
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "resourceType": item.get("resourceType", ""),
        "componentType": item.get("componentType", ""),
        "status": item.get("status", ""),
        "osType": item.get("osType", ""),
        "osDescription": item.get("osDescription", ""),
        "isAgentInstalled": item.get("isAgentInstalled"),
        "monitorEnabled": item.get("monitorEnabled"),
        "externalId": item.get("externalId", ""),
        "nodeInstanceId": item.get("nodeInstanceId", ""),
    }


def search_resource_summaries(
    *,
    base_url,
    headers,
    request_fn=request_json,
    params=None,
    payload=None,
):
    search_payload = request_fn(
        "POST",
        "/nodes/search",
        base_url=base_url,
        headers=headers,
        params=params,
        payload=payload,
    )
    search_items = extract_list_payload(search_payload)
    return [
        normalize_resource_summary(item)
        for item in search_items
        if isinstance(item, dict)
    ]


def collect_resource_ids_from_summaries(
    resource_summaries,
    *,
    expected_name="",
    preferred_external_id="",
    preferred_node_instance_id="",
):
    candidates = []
    for item in resource_summaries:
        if not isinstance(item, dict):
            continue
        if expected_name and item.get("name") != expected_name:
            continue
        candidates.append(item)

    if preferred_node_instance_id:
        node_matches = [
            item for item in candidates
            if item.get("nodeInstanceId") == preferred_node_instance_id
        ]
        if node_matches:
            candidates = node_matches

    if preferred_external_id:
        external_matches = [
            item for item in candidates
            if item.get("externalId") == preferred_external_id
        ]
        if external_matches:
            candidates = external_matches

    if expected_name and len(candidates) != 1:
        return []

    resource_ids = []
    for item in candidates:
        resource_id = item.get("id")
        if resource_id in (None, ""):
            continue
        resource_id = str(resource_id)
        if resource_id not in resource_ids:
            resource_ids.append(resource_id)
    return resource_ids


def fetch_resource_record(resource_id, *, base_url, headers, request_fn):
    errors = []

    try:
        resource = request_fn(
            "GET",
            f"/nodes/{resource_id}",
            base_url=base_url,
            headers=headers,
        )
    except RuntimeError as exc:
        return {
            "resourceId": resource_id,
            "summary": {},
            "resource": {},
            "details": {},
            "fetchStatus": "error",
            "errors": [str(exc)],
        }

    details = {}
    try:
        details = request_fn(
            "GET",
            f"/nodes/{resource_id}/details",
            base_url=base_url,
            headers=headers,
        )
        if not isinstance(details, dict):
            details = {}
    except RuntimeError as exc:
        errors.append(str(exc))

    return {
        "resourceId": resource_id,
        "summary": {},
        "resource": resource if isinstance(resource, dict) else {},
        "details": details,
        "normalized": {},
        "fetchStatus": "partial" if errors else "ok",
        "errors": errors,
    }


def build_missing_record(resource_id):
    return {
        "resourceId": resource_id,
        "summary": {},
        "resource": {},
        "details": {},
        "normalized": {"type": "", "properties": {}},
        "fetchStatus": "not_found",
        "errors": ["Resource was not returned by /nodes/search."],
    }


def merge_first_wins(target: dict, source: dict) -> None:
    for key, value in source.items():
        if not key:
            continue
        if key in target:
            continue
        if value in (None, ""):
            continue
        target[key] = value


def _simple_fields(mapping: dict) -> dict:
    if not isinstance(mapping, dict):
        return {}
    result = {}
    for key, value in mapping.items():
        if isinstance(value, (dict, list)):
            continue
        result[key] = value
    return result


def _extract_runtime_properties(resource: dict) -> dict:
    runtime = {}
    direct_runtime = resource.get("RuntimeProperties")
    if isinstance(direct_runtime, dict):
        merge_first_wins(runtime, _simple_fields(direct_runtime))

    extensible = resource.get("extensibleProperties")
    if isinstance(extensible, dict):
        runtime_from_ext = extensible.get("RuntimeProperties")
        if isinstance(runtime_from_ext, dict):
            merge_first_wins(runtime, _simple_fields(runtime_from_ext))

    exts = resource.get("exts")
    if isinstance(exts, dict):
        custom = exts.get("customProperty")
        if isinstance(custom, dict):
            merge_first_wins(runtime, _simple_fields(custom))
    return runtime


def determine_component_type(record: dict) -> str:
    summary = record.get("summary") or {}
    resource = record.get("resource") or {}
    return (
        resource.get("componentType")
        or summary.get("componentType")
        or resource.get("resourceType")
        or summary.get("resourceType")
        or ""
    )


def build_flat_properties(record: dict) -> dict:
    summary = record.get("summary") or {}
    resource = record.get("resource") or {}
    details = record.get("details") or {}

    properties = {}

    # analysis-relevant top-level fields from resource first, then summary fallbacks.
    merge_first_wins(properties, _simple_fields(resource))
    merge_first_wins(properties, _simple_fields(summary))

    merge_first_wins(properties, _simple_fields(resource.get("properties") or {}))
    merge_first_wins(properties, _simple_fields(resource.get("resourceInfo") or {}))
    merge_first_wins(properties, _extract_runtime_properties(resource))
    merge_first_wins(properties, _simple_fields(resource.get("customProperties") or {}))
    merge_first_wins(properties, _simple_fields(details))
    merge_first_wins(properties, _simple_fields(resource.get("extra") or {}))

    return properties


def build_normalized_resource(record: dict) -> dict:
    return {
        "type": determine_component_type(record),
        "properties": build_flat_properties(record),
    }


def load_resource_records(resource_ids, *, base_url, headers, request_fn=request_json):
    search_items = search_resource_summaries(
        base_url=base_url,
        headers=headers,
        request_fn=request_fn,
        payload={"ids": resource_ids},
    )
    summary_by_id = {
        item.get("id", ""): item
        for item in search_items
        if item.get("id")
    }

    records = []
    for resource_id in resource_ids:
        if resource_id not in summary_by_id:
            records.append(build_missing_record(resource_id))
            continue

        record = fetch_resource_record(
            resource_id,
            base_url=base_url,
            headers=headers,
            request_fn=request_fn,
        )
        record["summary"] = summary_by_id[resource_id]
        record["normalized"] = build_normalized_resource(record)
        records.append(record)

    return records


def render_output(items):
    lines = [f"Found {len(items)} resource(s).", ""]

    for index, item in enumerate(items, start=1):
        summary = item.get("summary", {})
        resource = item.get("resource", {})
        name = (
            resource.get("name")
            or summary.get("name")
            or item.get("resourceId")
            or "unknown-resource"
        )
        status = item.get("fetchStatus", "unknown")
        lines.append(f"[{index}] {name} | {item.get('resourceId', '')} | {status}")

    lines.extend(
        [
            "",
            "##RESOURCE_META_START##",
            json.dumps(items, ensure_ascii=False),
            "##RESOURCE_META_END##",
        ]
    )
    return "\n".join(lines)


def list_all_resources(*, base_url, headers, request_fn=request_json, page=1, size=50):
    """List all resources with pagination."""
    result = request_fn(
        "POST",
        "/nodes/search",
        base_url=base_url,
        headers=headers,
        params={"page": page, "size": size},
        payload={},
    )
    items = extract_list_payload(result)
    total = result.get("totalElements", len(items)) if isinstance(result, dict) else len(items)
    return [
        normalize_resource_summary(item)
        for item in items
        if isinstance(item, dict)
    ], total


def main(argv=None) -> int:
    args = parse_args(argv)
    base_url, _, headers, _ = require_config()

    # If no resource IDs provided, list all resources
    if not args.resource_ids:
        try:
            items, total = list_all_resources(
                base_url=base_url,
                headers=headers,
                request_fn=request_json,
                page=args.page,
                size=args.size,
            )
        except (RuntimeError, RequestException) as exc:
            print(f"[ERROR] {exc}")
            return 1

        print(f"Found {total} resource(s), showing {len(items)} (page {args.page}):\n")
        for i, item in enumerate(items, start=1):
            name = item.get("name", "N/A")
            rid = item.get("id", "N/A")
            rtype = item.get("resourceType", "N/A")
            status = item.get("status", "N/A")
            print(f"  [{i}] {name} | {rid} | {rtype} | {status}")
        print()
        print("##RESOURCE_META_START##")
        print(json.dumps(items, ensure_ascii=False))
        print("##RESOURCE_META_END##")
        return 0

    # Query specific resources by ID
    try:
        records = load_resource_records(
            args.resource_ids,
            base_url=base_url,
            headers=headers,
            request_fn=request_json,
        )
    except (RuntimeError, RequestException) as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(render_output(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
