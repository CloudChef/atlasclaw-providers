"""Normalized SmartCMP resource detail views."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from smartcmp_provider.models.resources import (
    ResourceDetailView,
    ResourceDiskView,
    ResourceOperationView,
    ResourceSectionView,
)
from smartcmp_provider.domain.resource_actions import (
    available_resource_execution,
    available_resource_operations,
    normalize_operation_id,
)
from smartcmp_provider.domain.resource_normalization import (
    build_flat_resource_properties,
)


def build_resource_detail_view(
    resource_id: str,
    resource: dict[str, Any],
    *,
    category: str = "virtual-machines",
) -> ResourceDetailView:
    """Normalize raw SmartCMP resource detail into an adapter-neutral view."""

    properties = build_flat_resource_properties(
        {
            "data": resource,
            "resource": resource,
            "details": resource,
        }
    )
    name = str(
        first_present_for_keys(
            properties,
            ("name", "nameZh", "displayName", "instanceName", "externalName"),
        )
    )
    status = str(
        first_present_for_keys(
            properties,
            ("status", "powerState", "phase", "state"),
        )
    )
    cpu = normalize_cpu_count(properties)
    memory_gb = normalize_memory_gb(properties)
    sections: list[ResourceSectionView] = []
    _add_section(
        sections,
        "Basic Information",
        [
            ("Name", name),
            (
                "OS Hostname",
                first_present_for_keys(
                    properties,
                    ("hostName", "hostname", "fqdn"),
                ),
            ),
            (
                "Operating System",
                first_present_for_keys(
                    properties,
                    ("osDescription", "os", "osType", "guestOsFullName"),
                ),
            ),
            ("Image", first_present_for_keys(properties, ("imageName",))),
            ("SSH Port", first_present_for_keys(properties, ("sshPort",))),
            (
                "Last Started At",
                first_present_for_keys(properties, ("lastStartedDate",)),
            ),
        ],
    )
    _add_section(
        sections,
        "Attributes",
        [
            ("Cloud Resource Name", name),
            (
                "Cloud Resource ID",
                first_present_for_keys(properties, ("externalId", "id")),
            ),
            ("CPU", cpu),
            ("Memory (GB)", memory_gb),
            (
                "Disk Count",
                first_present_for_keys(
                    properties,
                    ("diskTotalNum", "diskNum", "diskCount"),
                ),
            ),
            ("Disk Capacity (GB)", normalize_storage_gb(properties)),
            (
                "Host",
                first_present_for_keys(
                    properties,
                    ("host", "physicalHostName"),
                ),
            ),
        ],
    )
    _add_section(
        sections,
        "Service Information",
        [
            (
                "Application Stack Name",
                first_present_for_keys(properties, ("deploymentName",)),
            ),
            (
                "Deployed At",
                first_present_for_keys(
                    properties,
                    ("createdDate", "createdAt"),
                ),
            ),
            (
                "Lease Type",
                first_present_for_keys(properties, ("payType", "leaseType")),
            ),
            (
                "Expires At",
                first_present_for_keys(
                    properties,
                    ("lease", "expireAt", "expiryDate"),
                ),
            ),
            (
                "Retained Until",
                first_present_for_keys(
                    properties,
                    ("retentionAt", "retainUntil"),
                ),
            ),
        ],
    )
    _add_section(
        sections,
        "Organization Information",
        [
            (
                "Business Group",
                first_present_for_keys(properties, ("businessGroupName",)),
            ),
            (
                "Owner",
                first_present_for_keys(properties, ("ownerName", "ownerId")),
            ),
        ],
    )
    _add_section(
        sections,
        "Platform Information",
        [
            (
                "Platform Type",
                first_present_for_keys(
                    properties,
                    ("cloudEntryType", "cloudProvider", "platform"),
                ),
            ),
            (
                "Platform Entry",
                first_present_for_keys(properties, ("cloudEntryName",)),
            ),
            (
                "Resource Pool",
                first_present_for_keys(properties, ("resourceBundleName",)),
            ),
            (
                "vCenter Server",
                first_present_for_keys(
                    properties,
                    ("vcenterServer", "vcenterHost"),
                ),
            ),
            (
                "Folder",
                first_present_for_keys(
                    properties,
                    ("vcenterFolder", "folder"),
                ),
            ),
            (
                "Datastore",
                first_present_for_keys(
                    properties,
                    ("imageName", "datastoreName"),
                ),
            ),
            (
                "Storage Policy",
                first_present_for_keys(
                    properties,
                    ("storagePolicy", "diskPolicy"),
                ),
            ),
        ],
    )
    _add_section(
        sections,
        "Physical Host Information",
        [
            (
                "Host",
                first_present_for_keys(
                    properties,
                    ("physicalHost", "physicalHostName"),
                ),
            ),
            (
                "Vendor",
                first_present_for_keys(
                    properties,
                    ("physicalManufacturer", "vendor"),
                ),
            ),
            (
                "Model",
                first_present_for_keys(
                    properties,
                    ("physicalModel", "model"),
                ),
            ),
            (
                "CPU Cores",
                first_present_for_keys(
                    properties,
                    ("physicalCpuCores", "cpuCores"),
                ),
            ),
            (
                "CPU Model",
                first_present_for_keys(
                    properties,
                    ("physicalCpuType", "cpuModel"),
                ),
            ),
            (
                "CPU Usage",
                first_present_for_keys(
                    properties,
                    ("physicalCpuUsage", "cpuUsage"),
                ),
            ),
            (
                "Memory Usage",
                first_present_for_keys(
                    properties,
                    ("physicalMemoryUsage", "memoryUsage"),
                ),
            ),
        ],
    )
    _add_section(
        sections,
        "Resource Environment",
        [
            (
                "Cloud Platform Type",
                first_present_for_keys(
                    properties,
                    ("cloudEntryType", "cloudProvider", "platform"),
                ),
            ),
            (
                "Cloud Entry",
                first_present_for_keys(properties, ("cloudEntryName",)),
            ),
            (
                "Resource Pool",
                first_present_for_keys(properties, ("resourceBundleName",)),
            ),
        ],
    )
    return ResourceDetailView(
        resource_id=str(first_present(resource.get("id"), resource_id)),
        name=name or str(first_present(resource.get("id"), resource_id)),
        status=status,
        cpu=cpu,
        memory_gb=memory_gb,
        ip_addresses=tuple(normalize_ip_addresses(properties)),
        sections=tuple(sections),
        disks=tuple(extract_disk_entries(resource, properties)),
        available_operations=available_resource_operations(
            str(first_present(resource.get("id"), resource_id)),
            category=category,
        ),
    )


def build_resource_operation_view(
    index: int,
    operation: dict[str, Any],
    *,
    resource_id: str,
    resource_category: str,
) -> ResourceOperationView:
    """Normalize one executable operation for every output adapter."""

    action_category = operation.get("actionCategory") or {}
    if isinstance(action_category, dict):
        category_name = str(action_category.get("name") or "")
    else:
        category_name = str(action_category or "")
    operation_id = normalize_operation_id(str(operation.get("id") or ""))
    name = str(operation.get("name") or "")
    name_zh = str(operation.get("nameZh") or "")
    executable_action = available_resource_execution(
        resource_id,
        operation_id,
        category=resource_category,
    )
    return ResourceOperationView(
        index=index,
        id=operation_id,
        name=name,
        name_zh=name_zh,
        display_name=name_zh or name or operation_id,
        category=category_name,
        type=str(operation.get("type") or ""),
        support_batch_action=bool(operation.get("supportBatchAction")),
        support_scheduled_task=bool(
            operation.get("supportScheduledTask")
        ),
        available_operations=(executable_action,) if executable_action else (),
    )


def first_present(*values: Any) -> Any:
    """Return the first meaningful SmartCMP field value."""

    for value in values:
        if value not in (None, "", [], {}):
            return value
    return ""


def first_present_for_keys(
    properties: dict[str, Any],
    keys: Iterable[str],
) -> Any:
    """Return the first meaningful value among ordered property aliases."""

    return first_present(*(properties.get(key) for key in keys))


def parse_number(value: Any) -> float | None:
    """Parse a SmartCMP numeric field without guessing a unit."""

    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def format_decimal(value: float | None) -> str:
    """Render one normalized numeric value with at most two decimals."""

    if value is None:
        return ""
    rounded = round(value, 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def normalize_memory_gb(properties: dict[str, Any]) -> str:
    """Normalize known SmartCMP memory aliases to GB."""

    parsed = parse_number(
        first_present_for_keys(properties, ("memoryInGB", "memoryGB"))
    )
    if parsed is not None:
        return format_decimal(parsed)
    parsed = parse_number(
        first_present_for_keys(
            properties,
            ("memoryInMB", "memoryMb", "memoryMB"),
        )
    )
    if parsed is not None:
        return format_decimal(parsed / 1024.0)
    parsed = parse_number(
        first_present_for_keys(properties, ("memory", "memorySize"))
    )
    if parsed is None:
        return ""
    return format_decimal(parsed / 1024.0 if parsed > 64 else parsed)


def normalize_cpu_count(properties: dict[str, Any]) -> str:
    """Normalize known SmartCMP CPU aliases."""

    return format_decimal(
        parse_number(
            first_present_for_keys(
                properties,
                ("cpus", "cpu", "vcpu", "numCpu", "cores"),
            )
        )
    )


def normalize_storage_gb(properties: dict[str, Any]) -> str:
    """Normalize known SmartCMP storage aliases to GB."""

    parsed = parse_number(
        first_present_for_keys(
            properties,
            (
                "storageInGB",
                "storageGB",
                "totalStorageInGB",
                "serverStorageInGb",
                "diskTotalSizeGb",
                "storage",
                "diskTotalSize",
                "diskSize",
            ),
        )
    )
    if parsed is None:
        return ""
    if parsed > 100000:
        parsed /= 1024.0 * 1024.0 * 1024.0
    return format_decimal(parsed)


def normalize_ip_addresses(properties: dict[str, Any]) -> list[str]:
    """Collect stable, de-duplicated resource network addresses."""

    values = [
        str(properties.get(key))
        for key in (
            "ip",
            "ipAddress",
            "privateIp",
            "privateIpAddress",
            "publicIp",
            "publicIpAddress",
            "host",
        )
        if properties.get(key) not in (None, "")
    ]
    extra = properties.get("allNetworkAddresses")
    if isinstance(extra, list):
        values.extend(str(item) for item in extra if item not in (None, ""))
    elif isinstance(extra, str):
        values.extend(part.strip() for part in extra.split(",") if part.strip())
    return list(dict.fromkeys(values))


def extract_disk_entries(
    resource: dict[str, Any],
    properties: dict[str, Any],
) -> list[ResourceDiskView]:
    """Normalize explicit disk rows or a single aggregate fallback."""

    nested_properties = resource.get("properties")
    nested_properties = (
        nested_properties if isinstance(nested_properties, dict) else {}
    )
    for key in ("disks", "diskInfos", "diskInfoList", "diskList"):
        candidates = first_present(
            resource.get(key),
            nested_properties.get(key),
        )
        if not isinstance(candidates, list):
            continue
        rows: list[ResourceDiskView] = []
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
                size = format_decimal(
                    size_number / (1024.0 * 1024.0 * 1024.0)
                )
            rows.append(
                ResourceDiskView(
                    name=str(first_present(item.get("name"), f"Disk {index}")),
                    type=str(
                        first_present(
                            item.get("type"),
                            item.get("diskType"),
                            "",
                        )
                    ),
                    mode=str(
                        first_present(
                            item.get("mode"),
                            item.get("provisionMode"),
                            item.get("diskProvisionMode"),
                            "",
                        )
                    ),
                    size_gb=str(first_present(size, "")),
                )
            )
        if rows:
            return rows
    storage_gb = normalize_storage_gb(properties)
    disk_count = first_present_for_keys(
        properties,
        ("diskTotalNum", "diskNum", "diskCount"),
    )
    if not storage_gb and not disk_count:
        return []
    return [
        ResourceDiskView(
            name="Disk 1",
            type=str(
                first_present_for_keys(
                    properties,
                    ("imageName", "diskPolicy"),
                )
            ),
            mode=str(
                first_present_for_keys(
                    properties,
                    ("diskProvisionMode",),
                )
            ),
            size_gb=storage_gb,
        )
    ]


def _add_section(
    sections: list[ResourceSectionView],
    title: str,
    rows: list[tuple[str, Any]],
) -> None:
    normalized = tuple(
        (label, str(value))
        for label, value in rows
        if value not in (None, "", [], {})
    )
    if normalized:
        sections.append(ResourceSectionView(title=title, rows=normalized))
