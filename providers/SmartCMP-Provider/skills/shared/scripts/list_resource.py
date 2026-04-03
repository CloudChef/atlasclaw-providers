#!/usr/bin/env python3
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

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _common import require_config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="List SmartCMP resource details by resource ID."
    )
    parser.add_argument("resource_ids", nargs="+")
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
    }


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
        "fetchStatus": "partial" if errors else "ok",
        "errors": errors,
    }


def build_missing_record(resource_id):
    return {
        "resourceId": resource_id,
        "summary": {},
        "resource": {},
        "details": {},
        "fetchStatus": "not_found",
        "errors": ["Resource was not returned by /nodes/search."],
    }


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


def main(argv=None) -> int:
    args = parse_args(argv)
    base_url, _, headers, _ = require_config()

    try:
        search_payload = request_json(
            "POST",
            "/nodes/search",
            base_url=base_url,
            headers=headers,
            payload={"ids": args.resource_ids},
        )
    except (RuntimeError, RequestException) as exc:
        print(f"[ERROR] {exc}")
        return 1

    search_items = extract_list_payload(search_payload)
    summary_by_id = {
        item.get("id", ""): normalize_resource_summary(item)
        for item in search_items
        if item.get("id")
    }

    records = []
    for resource_id in args.resource_ids:
        if resource_id not in summary_by_id:
            records.append(build_missing_record(resource_id))
            continue

        record = fetch_resource_record(
            resource_id,
            base_url=base_url,
            headers=headers,
            request_fn=request_json,
        )
        record["summary"] = summary_by_id[resource_id]
        records.append(record)

    print(render_output(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
