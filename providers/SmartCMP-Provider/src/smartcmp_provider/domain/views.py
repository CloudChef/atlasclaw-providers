"""Safe projections from raw SmartCMP records to shared typed views."""

from __future__ import annotations

from typing import Any

from smartcmp_provider.models.approvals import (
    ApprovalDetailResult,
    ApprovalListResult,
)
from smartcmp_provider.models.catalogs import CatalogItemsResult
from smartcmp_provider.models.requests import RequestStatusResult
from smartcmp_provider.models.views import (
    ApprovalDetailView,
    ApprovalRequestEvidence,
    FlavorEvidence,
    PendingApprovalListView,
    RequestStatusView,
)
from smartcmp_provider.domain.approval_context import (
    available_approval_operations,
    get_approver_info,
)
from smartcmp_provider.domain.approval_validation import request_ids_from_item


def project_request_status(result: RequestStatusResult) -> RequestStatusView:
    """Project normalized request metadata and omit the raw internal detail."""

    metadata = result.metadata
    return RequestStatusView(
        request_id=_text(metadata.get("requestId")),
        name=_text(metadata.get("name")),
        catalog_name=_text(metadata.get("catalogName")),
        state=_text(metadata.get("state")),
        provision_state=_text(metadata.get("provisionState")),
        status_category=_text(metadata.get("statusCategory")),
        approval_passed=_optional_bool(metadata.get("approvalPassed")),
        current_step=_text(metadata.get("currentStep")),
        current_approver=_text(metadata.get("currentApprover")),
        error=_text(metadata.get("error")),
        resource_ids=tuple(
            _text(item)
            for item in metadata.get("resourceIds") or ()
            if _text(item)
        ),
        created_date=_optional_int(metadata.get("createdDate")),
        created_at=_text(metadata.get("createdAt")),
        updated_date=_optional_int(metadata.get("updatedDate")),
        updated_at=_text(metadata.get("updatedAt")),
    )


def project_pending_list(result: ApprovalListResult) -> PendingApprovalListView:
    """Project raw pending rows into user-relevant approval evidence."""

    return PendingApprovalListView(
        items=tuple(project_approval_item(item) for item in result.items),
        total=result.total,
    )


def project_approval_detail(result: ApprovalDetailResult) -> ApprovalDetailView:
    """Project one resolved pending row without internal activity lookup IDs."""

    return ApprovalDetailView(
        request_id=result.request_id,
        request=project_approval_item(
            result.item,
            request_id=result.request_id,
        ),
    )


def project_approval_item(
    item: dict[str, Any],
    *,
    request_id: str = "",
) -> ApprovalRequestEvidence:
    """Extract user-visible analysis facts from one raw pending row."""

    activity = _mapping(item.get("currentActivity"))
    process_step = _mapping(activity.get("processStep"))
    request_params = _mapping(activity.get("requestParams"))
    extensible = _mapping(request_params.get("extensibleParameters"))
    compute = _compute_parameters(extensible)
    visible_ids = request_ids_from_item(item)
    visible_request_id = request_id or (
        visible_ids[0] if visible_ids else ""
    )
    specifications = {
        key: value
        for key, value in {
            "cpu": _nested_value(compute, "cpus"),
            "memory_mb": _nested_value(compute, "memory"),
            "compute_profile_id": _nested_value(
                compute,
                "compute_profile_id",
            ),
            "logic_template_id": _nested_value(
                compute,
                "logic_template_id",
            ),
            "physical_template_id": _nested_value(
                compute,
                "physical_template_id",
            ),
            "template_id": _nested_value(compute, "template_id"),
            "system_disk_gb": _nested_path(
                compute,
                "system_disk_config",
                "size",
            ),
            "resource_bundle_id": _nested_path(
                compute,
                "resource_bundle_config",
                "policy_resource",
            ),
            "ip_address": _first_matching_value(
                request_params,
                suffix="_ip_address",
            ),
            "backup_enabled": _nested_value(compute, "enable_backup"),
            "agent_install_method": _text(
                request_params.get(
                    "_ra_Compute_agent_config_install_method"
                )
            ),
        }.items()
        if value not in (None, "", [], {})
    }
    applicant = item.get("applicant")
    if isinstance(applicant, dict):
        applicant = applicant.get("name") or applicant.get("loginId")
    return ApprovalRequestEvidence(
        request_id=visible_request_id,
        name=_text(item.get("name")),
        catalog_name=_text(item.get("catalogName")),
        description=_text(item.get("description")),
        state=_text(activity.get("state") or item.get("state")),
        approval_step=_text(process_step.get("name")),
        current_approver=get_approver_info(item),
        applicant=_text(applicant),
        created_date=_optional_int(item.get("createdDate")),
        updated_date=_optional_int(
            activity.get("updatedDate") or item.get("updatedDate")
        ),
        business_justification=_text(
            activity.get("businessJustification")
            or request_params.get("deploymentReason")
        ),
        resource_specifications=specifications,
        available_operations=available_approval_operations(visible_request_id),
    )


def project_flavors(
    result: CatalogItemsResult,
) -> tuple[FlavorEvidence, ...]:
    """Project flavor records into approval-relevant specifications."""

    projected: list[FlavorEvidence] = []
    for item in result.items:
        projected.append(
            FlavorEvidence(
                id=_text(item.get("id")),
                name=_text(item.get("name") or item.get("nameZh")),
                cpu=_optional_int(
                    item.get("cpu")
                    or item.get("cpus")
                    or item.get("cpuNumber")
                ),
                memory_mb=_optional_int(
                    item.get("memoryMB")
                    or item.get("memory")
                    or item.get("memoryMb")
                ),
            )
        )
    return tuple(projected)


def _nested_value(mapping: dict[str, Any], key: str) -> Any:
    value = mapping.get(key)
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _nested_path(mapping: dict[str, Any], *keys: str) -> Any:
    current: Any = mapping
    for key in keys:
        current = _nested_value(_mapping(current), key)
    return current


def _first_matching_value(mapping: dict[str, Any], *, suffix: str) -> Any:
    for key, value in mapping.items():
        if key.endswith(suffix):
            return value
    return None


def _compute_parameters(extensible: dict[str, Any]) -> dict[str, Any]:
    named = _mapping(extensible.get("Compute"))
    if named:
        return named
    for key, value in extensible.items():
        if str(key or "").rsplit(".", 1)[-1].casefold() != "compute":
            continue
        candidate = _mapping(value)
        if candidate:
            return candidate
    return {}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
