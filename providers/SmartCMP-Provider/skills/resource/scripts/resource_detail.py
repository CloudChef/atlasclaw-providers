# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Refresh and render one SmartCMP resource or cloud host by ID or exact name."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPTS_DIR = SCRIPT_DIR.parents[1] / "shared" / "scripts"
if str(SHARED_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS_DIR))

from _common import request_timeout, require_config  # noqa: E402
from _resource_object_actions import build_resource_object_actions  # noqa: E402


RESOURCE_NAME_SEARCH_SIZE = 100
RESOURCE_NAME_SEARCH_MAX_PAGES = 20


class ResourceResolutionError(ValueError):
    """User-facing resource target resolution error that avoids exposing internal IDs."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh and render one SmartCMP resource or cloud host."
    )
    parser.add_argument("resource_id", nargs="?", help="SmartCMP resource ID.")
    parser.add_argument(
        "--resource-id",
        dest="resource_id_option",
        default="",
        help="SmartCMP resource ID for callers that pass named CLI options.",
    )
    parser.add_argument(
        "--resource-name",
        default="",
        help="Exact visible SmartCMP cloud host name to resolve before inspection.",
    )
    return parser.parse_args(argv)


def _build_virtual_machine_search_url(base_url: str, *, query_value: str, page: int) -> str:
    encoded_query_value = quote(query_value or "", safe="")
    return (
        f"{base_url}/nodes/search"
        f"?query&page={page}&size={RESOURCE_NAME_SEARCH_SIZE}&catalogGroupIds=&sort=createdDate%2Cdesc"
        f"&queryValue={encoded_query_value}&category=iaas.machine.virtual_machine"
        f"&componentType=&monitorEnabled=&cloudEntryType=&isAgentInstalled=&os="
        f"&groupIds=&isImported=&relation=AND&fullMatch=true"
    )


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("content", "data", "items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            nested_items = _extract_items(value)
            if nested_items:
                return nested_items
    return []


def _extract_total_count(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("totalElements", "total", "totalCount", "count"):
        value = payload.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    for key in ("data", "result"):
        value = payload.get(key)
        nested_total = _extract_total_count(value)
        if nested_total is not None:
            return nested_total
    return None


def _display_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("nameZh")
        or item.get("displayName")
        or item.get("label")
        or item.get("instanceName")
        or "unknown resource"
    ).strip()


def _display_status(item: dict[str, Any]) -> str:
    return str(
        item.get("status")
        or item.get("powerState")
        or item.get("state")
        or item.get("phase")
        or "unknown"
    ).strip()


def _escape_markdown_cell(value: object) -> str:
    rendered = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    rendered = " ".join(rendered.split())
    return rendered.replace("|", "\\|")


def _format_resource_choices(items: Iterable[dict[str, Any]]) -> str:
    rows = []
    for index, item in enumerate(items, start=1):
        rows.append(
            "| "
            + " | ".join(
                _escape_markdown_cell(value)
                for value in (index, _display_name(item), _display_status(item))
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


def _resolve_unique_resource_id_by_name(
    resource_name: str,
    *,
    base_url: str,
    headers: dict[str, Any],
) -> str:
    normalized_name = resource_name.strip()
    if not normalized_name:
        raise ResourceResolutionError("Provide a non-empty resource name.")

    items: list[dict[str, Any]] = []
    total_count: int | None = None
    for page in range(1, RESOURCE_NAME_SEARCH_MAX_PAGES + 1):
        url = _build_virtual_machine_search_url(base_url, query_value=normalized_name, page=page)
        try:
            response = requests.get(url, headers=headers, verify=False, timeout=request_timeout())
            response.raise_for_status()
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ResourceResolutionError(
                f"Resource search returned invalid JSON. Status={response.status_code}, "
                f"Body={response.text[:200]}"
            ) from exc
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            response_body = ""
            if response is not None and getattr(response, "text", ""):
                response_body = f" Response body: {response.text[:400]}"
            raise ResourceResolutionError(f"Resource search failed: {exc}.{response_body}") from exc

        page_items = _extract_items(payload)
        items.extend(page_items)
        if total_count is None:
            total_count = _extract_total_count(payload)
        if total_count is not None:
            if len(items) >= total_count or not page_items:
                break
            continue
        if len(page_items) < RESOURCE_NAME_SEARCH_SIZE:
            break
    else:
        raise ResourceResolutionError(
            f"Too many virtual machines matched name '{normalized_name}'. Refine the resource name."
        )

    name_key = normalized_name.casefold()
    exact_matches = [
        item
        for item in items
        if _display_name(item).casefold() == name_key and str(item.get("id") or "").strip()
    ]

    if not exact_matches:
        choices = _format_resource_choices(items)
        if choices:
            raise ResourceResolutionError(
                f"No virtual machine exactly matched name '{normalized_name}'. "
                f"Closest visible matches:\n{choices}"
            )
        raise ResourceResolutionError(
            f"No virtual machine exactly matched name '{normalized_name}'."
        )

    if len(exact_matches) > 1:
        raise ResourceResolutionError(
            f"Multiple virtual machines exactly matched name '{normalized_name}'. "
            f"Choose one by table #:\n{_format_resource_choices(exact_matches)}"
        )

    return str(exact_matches[0].get("id") or "").strip()


def unwrap_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        for key in ("data", "result", "content", "item"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return {}


def merge_scalar_fields(target: dict[str, Any], source: Any) -> None:
    if not isinstance(source, dict):
        return
    for key, value in source.items():
        if key in target:
            continue
        if isinstance(value, (dict, list)):
            continue
        if value in (None, ""):
            continue
        target[key] = value


def collect_properties(resource: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    merge_scalar_fields(properties, resource)
    merge_scalar_fields(properties, resource.get("properties") or {})
    merge_scalar_fields(properties, resource.get("resourceInfo") or {})
    merge_scalar_fields(properties, resource.get("customProperties") or {})
    merge_scalar_fields(properties, resource.get("extra") or {})
    merge_scalar_fields(properties, resource.get("metadata") or {})
    merge_scalar_fields(properties, resource.get("statusInfo") or {})

    extensible = resource.get("extensibleProperties")
    if isinstance(extensible, dict):
        merge_scalar_fields(properties, extensible)
        merge_scalar_fields(properties, extensible.get("RuntimeProperties") or {})

    exts = resource.get("exts")
    if isinstance(exts, dict):
        merge_scalar_fields(properties, exts)
        merge_scalar_fields(properties, exts.get("customProperty") or {})

    runtime = resource.get("RuntimeProperties")
    if isinstance(runtime, dict):
        merge_scalar_fields(properties, runtime)

    return properties


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return ""


def first_present_for_keys(properties: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = properties.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def parse_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def format_decimal(value: float | None) -> str:
    if value is None:
        return ""
    rounded = round(value, 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def normalize_memory_gb(properties: dict[str, Any]) -> str:
    value = first_present_for_keys(properties, ("memoryInGB", "memoryGB"))
    parsed = parse_number(value)
    if parsed is not None:
        return format_decimal(parsed)

    value = first_present_for_keys(properties, ("memoryInMB", "memoryMb", "memoryMB"))
    parsed = parse_number(value)
    if parsed is not None:
        return format_decimal(parsed / 1024.0)

    parsed = parse_number(first_present_for_keys(properties, ("memory", "memorySize")))
    if parsed is None:
        return ""
    if parsed > 64:
        return format_decimal(parsed / 1024.0)
    return format_decimal(parsed)


def normalize_cpu_count(properties: dict[str, Any]) -> str:
    parsed = parse_number(
        first_present_for_keys(properties, ("cpus", "cpu", "vcpu", "numCpu", "cores"))
    )
    return format_decimal(parsed)


def normalize_storage_gb(properties: dict[str, Any]) -> str:
    value = first_present_for_keys(
        properties,
        (
            "storageInGB",
            "storageGB",
            "totalStorageInGB",
            "serverStorageInGb",
            "diskTotalSizeGb",
            "storage",
        ),
    )
    parsed = parse_number(value)
    if parsed is not None:
        if parsed > 100000:
            return format_decimal(parsed / (1024.0 * 1024.0 * 1024.0))
        return format_decimal(parsed)

    parsed = parse_number(first_present_for_keys(properties, ("diskTotalSize", "diskSize")))
    if parsed is None:
        return ""
    if parsed > 100000:
        return format_decimal(parsed / (1024.0 * 1024.0 * 1024.0))
    return format_decimal(parsed)


def normalize_ip_addresses(properties: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "ip",
        "ipAddress",
        "privateIp",
        "privateIpAddress",
        "publicIp",
        "publicIpAddress",
        "host",
    ):
        value = properties.get(key)
        if value not in (None, ""):
            values.append(str(value))

    extra = properties.get("allNetworkAddresses")
    if isinstance(extra, list):
        values.extend(str(item) for item in extra if item not in (None, ""))
    elif isinstance(extra, str) and extra.strip():
        values.extend(part.strip() for part in extra.split(",") if part.strip())

    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def extract_disk_entries(resource: dict[str, Any], properties: dict[str, Any]) -> list[dict[str, str]]:
    for key in ("disks", "diskInfos", "diskInfoList", "diskList"):
        candidates = first_present(resource.get(key), (resource.get("properties") or {}).get(key))
        if isinstance(candidates, list):
            rows: list[dict[str, str]] = []
            for index, item in enumerate(candidates, start=1):
                if not isinstance(item, dict):
                    continue
                size = first_present(
                    item.get("sizeGB"),
                    item.get("sizeGb"),
                    item.get("size"),
                    item.get("diskSize"),
                )
                size_number = parse_number(size)
                if size_number is not None and size_number > 100000:
                    size = format_decimal(size_number / (1024.0 * 1024.0 * 1024.0))
                rows.append(
                    {
                        "name": str(first_present(item.get("name"), f"Disk {index}")),
                        "type": str(first_present(item.get("type"), item.get("diskType"), "")),
                        "mode": str(
                            first_present(
                                item.get("mode"),
                                item.get("provisionMode"),
                                item.get("diskProvisionMode"),
                                "",
                            )
                        ),
                        "sizeGb": str(first_present(size, "")),
                    }
                )
            if rows:
                return rows

    disk_count = first_present_for_keys(properties, ("diskTotalNum", "diskNum", "diskCount"))
    storage_gb = normalize_storage_gb(properties)
    if not storage_gb and not disk_count:
        return []

    return [
        {
            "name": "Disk 1",
            "type": str(first_present_for_keys(properties, ("imageName", "diskPolicy"))),
            "mode": str(first_present_for_keys(properties, ("diskProvisionMode",))),
            "sizeGb": storage_gb,
        }
    ]


def add_section(
    sections: list[tuple[str, list[tuple[str, str]]]],
    title: str,
    rows: list[tuple[str, Any]],
) -> None:
    normalized_rows = [
        (label, str(value))
        for label, value in rows
        if value not in (None, "", [], {})
    ]
    if normalized_rows:
        sections.append((title, normalized_rows))


def build_view_model(resource_id: str, resource: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
    name = str(
        first_present_for_keys(
            properties,
            ("name", "nameZh", "displayName", "instanceName", "externalName"),
        )
    )
    status = str(first_present_for_keys(properties, ("status", "powerState", "phase", "state")))
    cpu = normalize_cpu_count(properties)
    memory_gb = normalize_memory_gb(properties)
    ip_addresses = normalize_ip_addresses(properties)
    disks = extract_disk_entries(resource, properties)

    sections: list[tuple[str, list[tuple[str, str]]]] = []
    add_section(
        sections,
        "Basic Information",
        [
            ("Name", name),
            ("OS Hostname", first_present_for_keys(properties, ("hostName", "hostname", "fqdn"))),
            (
                "Operating System",
                first_present_for_keys(
                    properties,
                    ("osDescription", "os", "osType", "guestOsFullName"),
                ),
            ),
            ("Image", first_present_for_keys(properties, ("imageName",))),
            ("SSH Port", first_present_for_keys(properties, ("sshPort",))),
            ("Last Started At", first_present_for_keys(properties, ("lastStartedDate",))),
        ],
    )
    add_section(
        sections,
        "Attributes",
        [
            ("Cloud Resource Name", name),
            ("Cloud Resource ID", first_present_for_keys(properties, ("externalId", "id"))),
            ("CPU", cpu),
            ("Memory (GB)", memory_gb),
            ("Disk Count", first_present_for_keys(properties, ("diskTotalNum", "diskNum", "diskCount"))),
            ("Disk Capacity (GB)", normalize_storage_gb(properties)),
            ("Host", first_present_for_keys(properties, ("host", "physicalHostName"))),
        ],
    )
    add_section(
        sections,
        "Service Information",
        [
            ("Application Stack Name", first_present_for_keys(properties, ("deploymentName",))),
            ("Deployed At", first_present_for_keys(properties, ("createdDate", "createdAt"))),
            ("Lease Type", first_present_for_keys(properties, ("payType", "leaseType"))),
            ("Expires At", first_present_for_keys(properties, ("lease", "expireAt", "expiryDate"))),
            ("Retained Until", first_present_for_keys(properties, ("retentionAt", "retainUntil"))),
        ],
    )
    add_section(
        sections,
        "Organization Information",
        [
            ("Business Group", first_present_for_keys(properties, ("businessGroupName",))),
            ("Owner", first_present_for_keys(properties, ("ownerName", "ownerId"))),
        ],
    )
    add_section(
        sections,
        "Platform Information",
        [
            (
                "Platform Type",
                first_present_for_keys(properties, ("cloudEntryType", "cloudProvider", "platform")),
            ),
            ("Platform Entry", first_present_for_keys(properties, ("cloudEntryName",))),
            ("Resource Pool", first_present_for_keys(properties, ("resourceBundleName",))),
            ("vCenter Server", first_present_for_keys(properties, ("vcenterServer", "vcenterHost"))),
            ("Folder", first_present_for_keys(properties, ("vcenterFolder", "folder"))),
            ("Datastore", first_present_for_keys(properties, ("imageName", "datastoreName"))),
            ("Storage Policy", first_present_for_keys(properties, ("storagePolicy", "diskPolicy"))),
        ],
    )
    add_section(
        sections,
        "Physical Host Information",
        [
            ("Host", first_present_for_keys(properties, ("physicalHost", "physicalHostName"))),
            ("Vendor", first_present_for_keys(properties, ("physicalManufacturer", "vendor"))),
            ("Model", first_present_for_keys(properties, ("physicalModel", "model"))),
            ("CPU Cores", first_present_for_keys(properties, ("physicalCpuCores", "cpuCores"))),
            ("CPU Model", first_present_for_keys(properties, ("physicalCpuType", "cpuModel"))),
            ("CPU Usage", first_present_for_keys(properties, ("physicalCpuUsage", "cpuUsage"))),
            ("Memory Usage", first_present_for_keys(properties, ("physicalMemoryUsage", "memoryUsage"))),
        ],
    )
    add_section(
        sections,
        "Resource Environment",
        [
            (
                "Cloud Platform Type",
                first_present_for_keys(properties, ("cloudEntryType", "cloudProvider", "platform")),
            ),
            ("Cloud Entry", first_present_for_keys(properties, ("cloudEntryName",))),
            ("Resource Pool", first_present_for_keys(properties, ("resourceBundleName",))),
        ],
    )

    return {
        "resourceId": str(first_present(resource.get("id"), resource_id)),
        "name": name or str(first_present(resource.get("id"), resource_id)),
        "status": status,
        "cpu": cpu,
        "memoryGb": memory_gb,
        "ipAddresses": ip_addresses,
        "sections": sections,
        "disks": disks,
    }


def render_human_summary(view: dict[str, Any]) -> str:
    lines = [view["name"]]

    overview_rows = [
        ("Status", view.get("status", "")),
        (
            "Compute",
            " / ".join(
                part
                for part in (
                    f"{view['cpu']} CPU" if view.get("cpu") else "",
                    f"{view['memoryGb']} GB" if view.get("memoryGb") else "",
                )
                if part
            ),
        ),
        ("IP Address", ", ".join(view.get("ipAddresses") or [])),
    ]
    for label, value in overview_rows:
        if value:
            lines.append(f"- {label}: {value}")

    for title, rows in view.get("sections", []):
        lines.extend(["", title])
        for label, value in rows:
            lines.append(f"- {label}: {value}")

    disks = view.get("disks") or []
    if disks:
        lines.extend(["", "Disks"])
        for item in disks:
            details = [
                item.get("sizeGb", ""),
                item.get("type", ""),
                item.get("mode", ""),
            ]
            rendered = " | ".join(part for part in details if part)
            if rendered:
                lines.append(f"- {item.get('name', 'Disk')}: {rendered}")
            else:
                lines.append(f"- {item.get('name', 'Disk')}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base_url, _auth_token, headers, _instance = require_config()
    resource_id = str(args.resource_id or args.resource_id_option or "").strip()
    resource_name = str(args.resource_name or "").strip()
    if not resource_id and resource_name:
        try:
            resource_id = _resolve_unique_resource_id_by_name(
                resource_name,
                base_url=base_url,
                headers=headers,
            )
        except ResourceResolutionError as exc:
            print(f"[ERROR] {exc}")
            return 1
    if not resource_id:
        print("[ERROR] Provide either resource_id or resource_name.")
        return 1

    encoded_id = quote(resource_id, safe="")
    url = f"{base_url}/nodes/{encoded_id}/view"

    try:
        # SmartCMP currently exposes this read-only view through PATCH. The
        # endpoint is expected to become GET after the CMP API bug is fixed.
        response = requests.patch(url, headers=headers, verify=False, timeout=request_timeout())
        response.raise_for_status()
        payload = response.json()
    except json.JSONDecodeError:
        print(
            f"[ERROR] API returned invalid JSON. Status={response.status_code}, "
            f"Body={response.text[:200]}"
        )
        return 1
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        response_body = ""
        if response is not None and getattr(response, "text", ""):
            response_body = f" Response body: {response.text[:400]}"
        print(f"[ERROR] Request failed: {exc}.{response_body}")
        return 1

    resource = unwrap_payload(payload)
    properties = collect_properties(resource)
    view = build_view_model(resource_id, resource, properties)
    print(render_human_summary(view))
    meta = {
        "object_type": "virtual_machine",
        "object_id": view["resourceId"],
        "object_name": view["name"],
        # Detail pages can offer follow-up analysis and operation discovery.
        # They are still declared as generic object actions so the renderer does
        # not need SmartCMP-specific branching.
        "object_actions": build_resource_object_actions(
            base_url,
            view["resourceId"],
            resource_name=view["name"],
            include_analysis_action=True,
            include_operations_action=True,
        ),
        "resourceId": view["resourceId"],
        "name": view["name"],
    }
    print("##RESOURCE_DETAIL_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print("##RESOURCE_DETAIL_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
