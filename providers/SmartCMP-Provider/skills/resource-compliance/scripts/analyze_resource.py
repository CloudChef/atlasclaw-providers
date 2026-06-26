#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Analyze one or more SmartCMP resources for compliance risk."""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

import requests


def _load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load module from path: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_SCRIPT_DIR = os.path.join(SCRIPT_DIR, "..", "..", "shared", "scripts")
DATASOURCE_SCRIPT_DIR = os.path.join(SCRIPT_DIR, "..", "..", "datasource", "scripts")

analysis_module = _load_module_from_path(
    "resource_compliance_analysis_local",
    os.path.join(SCRIPT_DIR, "_analysis.py"),
)
analyze_normalized_resource = analysis_module.analyze_normalized_resource
build_analysis_facts = analysis_module.build_analysis_facts
build_normalized_from_legacy_facts = analysis_module.build_normalized_from_legacy_facts

common_module = _load_module_from_path(
    "resource_compliance_common_local",
    os.path.join(SHARED_SCRIPT_DIR, "_common.py"),
)
require_config = common_module.require_config
build_resource_object_actions = common_module.build_resource_object_actions
request_timeout = common_module.request_timeout

list_resource_module = _load_module_from_path(
    "resource_compliance_list_resource_local",
    os.path.join(DATASOURCE_SCRIPT_DIR, "list_resource.py"),
)
load_resource_records = list_resource_module.load_resource_records
request_json = list_resource_module.request_json
search_resource_summaries = list_resource_module.search_resource_summaries


class ResourceResolutionError(ValueError):
    """User-facing target resolution error that must not expose SmartCMP IDs."""


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze one or more SmartCMP resources for compliance risk."
    )
    parser.add_argument("positional_resource_ids", nargs="*")
    parser.add_argument("--resource-ids", nargs="*", default=[])
    parser.add_argument("--resource-name", action="append", default=[])
    parser.add_argument("--resource-index")
    parser.add_argument("--resource-directory-json")
    parser.add_argument("--trigger-source", default="user")
    parser.add_argument("--payload-json")
    return parser.parse_args(argv)


def normalize_request(args):
    if args.payload_json:
        payload = json.loads(args.payload_json)
        resource_ids = _split_resource_id_values(
            payload.get("resourceIds") or payload.get("resource_ids") or []
        )
        resource_names = _normalize_resource_names(
            payload.get("resourceName")
            or payload.get("resource_name")
            or payload.get("resourceNames")
            or payload.get("resource_names")
            or []
        )
        resource_index = _parse_resource_index(
            _first_present(payload.get("resourceIndex"), payload.get("resource_index"))
        )
        resource_directory_json = (
            payload.get("resourceDirectory")
            or payload.get("resource_directory")
            or payload.get("resourceDirectoryJson")
            or payload.get("resource_directory_json")
            or ""
        )
        trigger_source = payload.get("triggerSource") or payload.get("trigger_source") or args.trigger_source
        raw_metadata = payload.get("rawMetadata") or payload
    else:
        resource_ids = _split_resource_id_values(args.resource_ids)
        resource_ids.extend(_split_resource_id_values(args.positional_resource_ids))
        resource_names = _normalize_resource_names(args.resource_name)
        resource_index = _parse_resource_index(args.resource_index)
        resource_directory_json = args.resource_directory_json
        trigger_source = args.trigger_source
        raw_metadata = {}

    directory_items = parse_resource_directory(resource_directory_json)
    resource_ids, requested_resources, resolved_resources = resolve_resource_targets(
        resource_ids=resource_ids,
        resource_names=resource_names,
        resource_index=resource_index,
        directory_items=directory_items,
        trigger_source=trigger_source,
    )

    return {
        "resourceIds": resource_ids,
        "requestedResources": requested_resources,
        "resolvedResources": resolved_resources,
        "triggerSource": trigger_source,
        "rawMetadata": raw_metadata,
    }


def _split_resource_id_values(values):
    """Return de-duplicated internal resource IDs from compatibility inputs."""
    if values in (None, ""):
        return []
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, (list, tuple, set)):
        raw_values = list(values)
    else:
        raw_values = [values]

    resource_ids = []
    for value in raw_values:
        for candidate in str(value).replace(",", " ").split():
            normalized = candidate.strip()
            if normalized and normalized not in resource_ids:
                resource_ids.append(normalized)
    return resource_ids


def _first_present(*values):
    """Return the first value that is not absent, preserving falsey user input."""
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _normalize_resource_names(values):
    """Return explicit resource names without splitting names that contain spaces."""
    if values in (None, ""):
        return []
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, (list, tuple, set)):
        raw_values = list(values)
    else:
        raw_values = [values]
    names = []
    for value in raw_values:
        normalized = str(value).strip()
        if normalized and normalized not in names:
            names.append(normalized)
    return names


def _parse_resource_index(value):
    """Parse a user-visible list index when one was provided."""
    if value in (None, ""):
        return None
    try:
        index = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ResourceResolutionError("Resource index must be a positive integer.") from exc
    if index <= 0:
        raise ResourceResolutionError("Resource index must be a positive integer.")
    return index


def parse_resource_directory(resource_directory_json):
    """Extract resource list metadata from a raw list or workflow-context JSON value."""
    if resource_directory_json in (None, ""):
        return []
    payload = resource_directory_json
    if isinstance(resource_directory_json, str):
        try:
            payload = json.loads(resource_directory_json)
        except json.JSONDecodeError as exc:
            raise ResourceResolutionError("Resource list metadata is not valid JSON.") from exc
    candidates = _extract_directory_items(payload)
    return [
        item for item in candidates
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]


def _extract_directory_items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("resources", "items", "metadata", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    recent_metadata = payload.get("recent_tool_metadata")
    if isinstance(recent_metadata, list):
        for entry in reversed(recent_metadata):
            if not isinstance(entry, dict):
                continue
            tool_name = str(entry.get("tool_name") or "").strip()
            metadata = entry.get("metadata")
            if tool_name == "smartcmp_list_all_resource" and isinstance(metadata, list):
                return metadata
        for entry in reversed(recent_metadata):
            if isinstance(entry, dict) and isinstance(entry.get("metadata"), list):
                return entry["metadata"]

    return []


def resolve_resource_targets(
    *,
    resource_ids,
    resource_names,
    resource_index,
    directory_items,
    trigger_source,
):
    """Resolve names or visible list indexes into internal SmartCMP resource IDs."""
    if resource_ids:
        return (
            resource_ids,
            [
                {"name": "", "index": None, "source": _request_source(trigger_source)}
                for _resource_id in resource_ids
            ],
            [
                {"name": "", "index": None, "status": "", "scope": "", "resourceId": resource_id}
                for resource_id in resource_ids
            ],
        )

    if directory_items and (resource_names or resource_index is not None):
        return resolve_from_directory(
            resource_names=resource_names,
            resource_index=resource_index,
            directory_items=directory_items,
        )

    if resource_index is not None:
        raise ResourceResolutionError(
            f"No recent resource list metadata is available for index {resource_index}. "
            "List resources first or provide the exact resource name."
        )

    if resource_names:
        return resolve_from_name_search(resource_names)

    raise ResourceResolutionError(
        "Provide an exact resource name or select a resource from the latest resource table."
    )


def _request_source(trigger_source):
    if str(trigger_source or "").strip().lower() == "webhook":
        return "webhook"
    return "resource_id"


def resolve_from_directory(*, resource_names, resource_index, directory_items):
    """Resolve a target from hidden metadata emitted by the resource list tool."""
    selected_items = []
    if resource_index is not None:
        selected = next(
            (
                item for item in directory_items
                if _safe_int(item.get("index")) == resource_index
            ),
            None,
        )
        if selected is None:
            raise ResourceResolutionError(
                f"No listed resource matched index {resource_index}. "
                f"Available resources:\n{format_resource_choices(directory_items)}"
            )
        selected_items = [selected]

    if resource_names:
        name_matches = [
            item for item in directory_items
            if display_name(item) in resource_names
        ]
        for name in resource_names:
            exact_matches = [
                item for item in directory_items
                if display_name(item) == name
            ]
            if not exact_matches:
                raise ResourceResolutionError(
                    f"No listed resource exactly matched name '{name}'. "
                    f"Available resources:\n{format_resource_choices(directory_items)}"
                )
            if len(exact_matches) > 1 and resource_index is None:
                raise ResourceResolutionError(
                    f"Multiple listed resources exactly matched name '{name}'. "
                    f"Choose one by table #:\n{format_resource_choices(exact_matches)}"
                )

        if selected_items:
            selected_name = display_name(selected_items[0])
            if selected_name not in resource_names:
                raise ResourceResolutionError(
                    f"Selected resource does not match the provided name. "
                    f"Index {resource_index} is '{selected_name}', "
                    f"but the requested name was '{resource_names[0]}'."
                )
        else:
            selected_items = name_matches

    return build_resolved_request(
        selected_items,
        source="resource_directory",
        include_request_index=resource_index is not None,
    )


def resolve_from_name_search(resource_names):
    """Resolve exact resource names through SmartCMP search when no list metadata exists."""
    resolved_items = []
    for name in resource_names:
        base_url, _, headers, _ = require_config()
        summaries = search_resource_summaries(
            base_url=base_url,
            headers=headers,
            request_fn=request_json,
            params={"page": 1, "size": 20, "queryValue": name},
            payload={},
        )
        exact_matches = [
            item for item in summaries
            if display_name(item) == name and str(item.get("id") or "").strip()
        ]
        if not exact_matches:
            choices = format_resource_choices(summaries)
            if choices:
                raise ResourceResolutionError(
                    f"No SmartCMP resource exactly matched name '{name}'. "
                    f"Closest visible matches:\n{choices}"
                )
            raise ResourceResolutionError(
                f"No SmartCMP resource exactly matched name '{name}'."
            )
        if len(exact_matches) > 1:
            raise ResourceResolutionError(
                f"Multiple SmartCMP resources exactly matched name '{name}'. "
                f"Choose one by table #:\n{format_resource_choices(exact_matches)}"
            )
        resolved_items.append(exact_matches[0])

    return build_resolved_request(
        resolved_items,
        source="resource_search",
        include_request_index=False,
    )


def build_resolved_request(items, *, source, include_request_index):
    """Build the internal IDs plus name-first request metadata."""
    resource_ids = []
    requested_resources = []
    resolved_resources = []

    for item in items:
        resource_id = str(item.get("id") or "").strip()
        if not resource_id or resource_id in resource_ids:
            continue
        resource_ids.append(resource_id)
        index = _safe_int(item.get("index"))
        name = display_name(item)
        requested_resources.append(
            {
                "name": name,
                "index": index if include_request_index else None,
                "source": source,
            }
        )
        resolved_resources.append(
            {
                "name": name,
                "index": index,
                "status": display_status(item),
                "scope": str(item.get("scope") or "").strip(),
                "resourceId": resource_id,
            }
        )

    if not resource_ids:
        raise ResourceResolutionError("No resolvable resource was selected.")
    return resource_ids, requested_resources, resolved_resources


def _safe_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def display_name(item):
    """Return the user-visible name for a resource directory entry."""
    return str(
        item.get("name")
        or item.get("nameZh")
        or item.get("displayName")
        or item.get("label")
        or item.get("instanceName")
        or "unknown resource"
    ).strip()


def display_status(item):
    """Return the user-visible status for a resource directory entry."""
    return str(
        item.get("status")
        or item.get("powerState")
        or item.get("state")
        or item.get("phase")
        or "unknown"
    ).strip()


def escape_markdown_cell(value):
    """Render a resource choice value safely inside a Markdown table cell."""
    rendered = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    rendered = " ".join(rendered.split())
    return rendered.replace("|", "\\|")


def format_resource_choices(items):
    """Render name/status choices as a Markdown table without exposing resource IDs."""
    rows = []
    for fallback_index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        index = _safe_int(item.get("index")) or fallback_index
        rows.append(
            "| "
            + " | ".join(
                escape_markdown_cell(value)
                for value in (index, display_name(item), display_status(item))
            )
            + " |"
        )
    if not rows:
        return ""
    return "\n".join([
        "| # | Name | Status |",
        "| --- | --- | --- |",
        *rows,
    ])


def load_resources(resource_ids):
    base_url, _, headers, _ = require_config()
    return load_resource_records(
        resource_ids,
        base_url=base_url,
        headers=headers,
        request_fn=request_json,
    )


def resolve_action_context():
    """Resolve the SmartCMP base URL used to build object actions."""
    try:
        base_url, _, _, _instance = require_config()
    except (Exception, SystemExit):
        return ""
    return base_url


def attach_resource_object_metadata(result, index, *, base_url=""):
    """Attach object identity and explicit resource actions to one analysis result."""
    resource_id = str(result.get("resourceId") or "").strip()
    resource_name = str(result.get("resourceName") or "").strip()
    object_name = resource_name or resource_id
    result.update(
        {
            "index": index,
            "object_type": "smartcmp_resource",
            "object_id": resource_id,
            "object_name": object_name,
            "object_actions": build_resource_object_actions(
                base_url,
                resource_id,
                resource_name=object_name,
                include_detail_action=True,
                include_analysis_action=True,
            ),
        }
    )
    return result


def external_checker(product, version):
    product = (product or "").lower()
    if product == "mysql":
        return check_mysql_support(version)
    if product == "windows":
        return check_windows_support(version)
    if product == "ubuntu":
        return check_ubuntu_support(version)
    return {
        "status": "unknown",
        "summary": f"No built-in authoritative checker is available yet for {product} {version}.",
        "links": [],
        "checkedAt": _now_iso(),
    }


def check_mysql_support(version):
    url = "https://www.mysql.com/support/eol-notice.html"
    text = fetch_text(url)
    lowered = text.lower()
    checked_at = _now_iso()

    if version.startswith("5.7") and "mysql 5.7 is covered under oracle lifetime sustaining support" in lowered:
        return {
            "status": "unsupported",
            "summary": "MySQL 5.7 is covered under Oracle Sustaining Support, which indicates regular standard support has ended.",
            "links": [url],
            "checkedAt": checked_at,
        }
    if version.startswith("8.0") and "mysql 8.0" in lowered and "eol in april 2026" in lowered:
        return {
            "status": "warning",
            "summary": "MySQL 8.0 is called out by the official MySQL EOL notice and approaches platform lifecycle limits.",
            "links": [url],
            "checkedAt": checked_at,
        }
    if version.startswith("8.4") and "mysql" in lowered:
        return {
            "status": "supported",
            "summary": "Official MySQL support pages are reachable; review the exact 8.4 support terms in Oracle documentation.",
            "links": [url],
            "checkedAt": checked_at,
        }

    return {
        "status": "unknown",
        "summary": f"Official MySQL support pages were reachable, but no exact lifecycle match was parsed for version {version}.",
        "links": [url],
        "checkedAt": checked_at,
    }


def check_windows_support(version):
    normalized_version = version.lower().replace(" ", "-")
    url = f"https://learn.microsoft.com/en-us/lifecycle/products/windows-server-{normalized_version}"
    markdown = fetch_text(url, accept="text/markdown")
    checked_at = _now_iso()
    match = re.search(
        r"\|\s*Windows Server [^|]+\|\s*[^|]+\|\s*([^|]+)\|\s*([^|]+)\|",
        markdown,
        flags=re.IGNORECASE,
    )
    if not match:
        return {
            "status": "unknown",
            "summary": f"Microsoft lifecycle content was reachable for Windows Server {version}, but support dates could not be parsed automatically.",
            "links": [url],
            "checkedAt": checked_at,
        }

    mainstream_end = match.group(1).strip()
    extended_end = match.group(2).strip()
    is_extended_expired = _is_past_iso_datetime(extended_end)

    if is_extended_expired:
        return {
            "status": "unsupported",
            "summary": f"Microsoft lists Windows Server {version} Extended End Date as {extended_end}.",
            "links": [url],
            "checkedAt": checked_at,
        }

    return {
        "status": "warning",
        "summary": f"Microsoft lists Windows Server {version} Mainstream End Date as {mainstream_end} and Extended End Date as {extended_end}.",
        "links": [url],
        "checkedAt": checked_at,
    }


def check_ubuntu_support(version):
    url = "https://ubuntu.com/about/release-cycle"
    text = fetch_text(url)
    checked_at = _now_iso()
    release_pattern = rf'"release":\s*"{re.escape(version)}(?:\s+LTS)?"'
    if not re.search(release_pattern, text, flags=re.IGNORECASE):
        return {
            "status": "unknown",
            "summary": f"Canonical release-cycle data was reachable, but Ubuntu {version} was not matched automatically.",
            "links": [url],
            "checkedAt": checked_at,
        }

    support_match = re.search(
        rf'"release":\s*"{re.escape(version)}(?:\s+LTS)?"[\s\S]{{0,1200}}?"supported":\s*\{{[\s\S]{{0,200}}?"raw":\s*"([^"]+)"',
        text,
        flags=re.IGNORECASE,
    )
    pro_match = re.search(
        rf'"release":\s*"{re.escape(version)}(?:\s+LTS)?"[\s\S]{{0,1200}}?"pro_supported":\s*\{{[\s\S]{{0,200}}?"raw":\s*"([^"]+)"',
        text,
        flags=re.IGNORECASE,
    )
    supported_until = support_match.group(1) if support_match else ""
    pro_until = pro_match.group(1) if pro_match else ""

    if supported_until and _is_past_date(supported_until):
        return {
            "status": "warning",
            "summary": f"Canonical lists Ubuntu {version} standard support until {supported_until}; check Ubuntu Pro/ESM coverage (listed as {pro_until or 'unknown'}).",
            "links": [url],
            "checkedAt": checked_at,
        }

    return {
        "status": "supported",
        "summary": f"Canonical release-cycle data lists Ubuntu {version} support through {supported_until or 'an available support window'}.",
        "links": [url],
        "checkedAt": checked_at,
    }


def fetch_text(url, accept="text/html"):
    headers = {
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
    }
    try:
        response = requests.get(url, headers=headers, timeout=request_timeout())
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        try:
            completed = subprocess.run(
                ["curl", "-LksS", "-H", f"Accept: {accept}", "-H", "Accept-Language: en-US,en;q=0.9", url],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(f"Failed to fetch external source: {url}") from exc
        if not completed.stdout:
            raise RuntimeError(f"External source returned no content: {url}")
        return completed.stdout


def build_failed_result(record):
    summary = record.get("summary") or {}
    resource = record.get("data") or record.get("resource") or {}
    normalized = record.get("normalized") or {}
    return {
        "resourceId": record.get("resourceId", ""),
        "sourceEndpoint": record.get("sourceEndpoint", ""),
        "resourceName": summary.get("name") or resource.get("name", ""),
        "resourceType": summary.get("resourceType") or resource.get("resourceType", ""),
        "type": normalized.get("type")
        or summary.get("componentType")
        or resource.get("componentType")
        or summary.get("resourceType")
        or resource.get("resourceType")
        or "",
        "properties": normalized.get("properties", {}),
        "analysisTargets": [],
        "analysisStatus": "fetch_failed",
        "findings": [],
        "summary": {
            "overallRisk": "medium",
            "overallCompliance": "needs_review",
            "confidence": "low",
        },
        "recommendations": ["Retry resource retrieval or inspect the resource directly in SmartCMP."],
        "missingEvidence": list(record.get("missingEvidence") or []),
        "uncertainties": record.get("errors", []),
    }


def normalize_record_for_analysis(record):
    normalized = record.get("normalized")
    if isinstance(normalized, dict) and normalized.get("type"):
        return normalized

    return build_normalized_from_legacy_facts(build_analysis_facts(record))


def render_output(payload):
    lines = [f"Analyzed {payload['analyzedCount']} resource(s)."]
    if payload["failedCount"]:
        lines.append(f"Failed to fully analyze {payload['failedCount']} resource(s).")
    lines.extend(
        [
            "",
            "| # | Resource | Compliance | Confidence |",
            "| --- | --- | --- | --- |",
        ]
    )

    for index, item in enumerate(payload["results"], start=1):
        resource_label = item.get("resourceName") or "unknown resource"
        lines.append(
            "| "
            + " | ".join(
                escape_markdown_cell(value)
                for value in (
                    index,
                    resource_label,
                    item["summary"]["overallCompliance"],
                    item["summary"]["confidence"],
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "##RESOURCE_COMPLIANCE_START##",
            json.dumps(payload, ensure_ascii=False),
            "##RESOURCE_COMPLIANCE_END##",
        ]
    )
    return "\n".join(lines)


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_past_iso_datetime(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt.astimezone(timezone.utc) < datetime.now(timezone.utc)


def _is_past_date(value):
    try:
        dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return dt < datetime.now(timezone.utc)


def main(argv=None) -> int:
    try:
        request = normalize_request(parse_args(argv))
    except (ResourceResolutionError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    try:
        resource_records = load_resources(request["resourceIds"])
    except Exception as exc:  # pragma: no cover - provider/network failures surface at runtime
        print(f"[ERROR] {exc}")
        return 1

    action_base_url = resolve_action_context()
    results = []
    analyzed_count = 0
    failed_count = 0
    for index, record in enumerate(resource_records, start=1):
        if record.get("fetchStatus") != "ok":
            results.append(
                attach_resource_object_metadata(
                    build_failed_result(record),
                    index,
                    base_url=action_base_url,
                )
            )
            failed_count += 1
            continue

        summary = record.get("summary") or {}
        resource = record.get("data") or record.get("resource") or {}
        normalized = normalize_record_for_analysis(record)
        result = analyze_normalized_resource(normalized, external_checker=external_checker)
        result.update(
            {
                "resourceId": record.get("resourceId", ""),
                "resourceName": resource.get("name") or summary.get("name", ""),
                "resourceType": resource.get("resourceType") or summary.get("resourceType", ""),
                "analysisStatus": "analyzed",
            }
        )
        if record.get("errors"):
            result["uncertainties"].extend(record["errors"])
        results.append(
            attach_resource_object_metadata(
                result,
                index,
                base_url=action_base_url,
            )
        )
        analyzed_count += 1

    payload = {
        "triggerSource": request["triggerSource"],
        "requestedResourceIds": request["resourceIds"],
        "requestedResources": request["requestedResources"],
        "resolvedResources": request["resolvedResources"],
        "analyzedCount": analyzed_count,
        "failedCount": failed_count,
        "generatedAt": _now_iso(),
        "results": results,
    }

    print(render_output(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
