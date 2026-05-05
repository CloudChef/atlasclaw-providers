# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
REQUEST_SKILL = PROVIDER_ROOT / "skills" / "request" / "SKILL.md"
APPROVAL_SKILL = PROVIDER_ROOT / "skills" / "approval" / "SKILL.md"


def test_request_skill_requires_datasource_business_group_resolution():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "smartcmp_list_available_bgs" in skill_text
    assert "Business-Group Resolution" in skill_text
    assert "if one BG, auto-select" in skill_text
    assert "MUST show list and WAIT for user to choose" in skill_text
    assert "uniquely normalizes to one available business group" in skill_text
    assert "If multiple business groups remain after normalization" in skill_text
    assert "do not repeat lookup scaffolding such as" in skill_text
    assert "`Found N business group(s)`" in skill_text


def test_request_skill_resolves_displayed_service_numbers_to_catalog_uuid():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Catalog identity contract" in skill_text
    assert "Displayed service list numbers are conversation choices only" in skill_text
    assert "resolve it against the latest" in skill_text
    assert "`smartcmp_list_services` result" in skill_text
    assert "catalog's metadata" in skill_text
    assert "`id`/`catalogId` UUID" in skill_text
    assert "Do not pass the" in skill_text
    assert "`service_id`, `catalog_id`, or `catalogId`" in skill_text
    assert "There is no tool named `smartcmp_get_catalog_questionnaire`" in skill_text
    assert "Never call `smartcmp_get_catalog_questionnaire`" in skill_text


def test_request_skill_does_not_trust_runtime_form_defaults_from_catalog_metadata():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "runtimeDefaultOnly" in skill_text
    assert "**NOT** serialize that value into the request body" in skill_text
    assert "let CMP runtime form apply the real default" in skill_text


def test_request_skill_requires_natural_language_follow_up_after_lookup_tools():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Natural-Language Follow-up After Lookup Tools" in skill_text
    assert "summarize the resolved result in natural language" in skill_text
    assert "ask at most one next question" in skill_text
    assert "ask exactly one natural-language question" in skill_text
    assert "Do not paste raw tool output" in skill_text
    assert "Never dump raw tool output" in skill_text


def test_request_skill_rejects_permissive_confirmation_language():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "brief confirmation like" not in skill_text
    assert "preferably as a numbered list" not in skill_text
    assert "Output a concise natural-language confirmation" in skill_text
    assert "Ask one concise selection question" in skill_text


def test_request_skill_follows_current_user_message_language():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "User Response Language" in skill_text
    assert "Use the current user's message language" in skill_text
    assert "English requests must get English follow-ups" in skill_text
    assert "Short summary of the request in the user's language" in skill_text
    assert "Short Chinese summary" not in skill_text
    assert "Ask `请确认以上信息是否正确？（是/否）`" not in skill_text


def test_request_skill_contracts_ticket_and_linux_vm_flow_expectations():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "after the ticket service is auto-selected and the business" in skill_text
    assert "continue with a" in skill_text
    assert "natural-language prompt for the remaining ticket fields" in skill_text
    assert "ask only the short business-group" in skill_text
    assert "recognize Linux VM, the business" in skill_text
    assert "carry those values forward" in skill_text
    assert "ask only for the remaining required fields" in skill_text
    assert "only when it is the unique" in skill_text
    assert "normalized datasource match" in skill_text


def test_request_skill_declares_provider_driven_workflow_metadata():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")
    success_contract = skill_text.split("tool_submit_success_contract:", 1)[1].split(
        "tool_status_name:",
        1,
    )[0]

    assert 'workflow_role: "request_parent"' in skill_text
    assert "tool_submit_success_contract:" in skill_text
    assert '- "requestId"' in success_contract
    assert '- "Request ID"' in success_contract
    assert '- "id"' not in success_contract
    assert "never expose UUID-shaped internal identifiers" in success_contract


def test_request_skill_declares_status_query_tool() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert 'tool_status_name: "smartcmp_get_request_status"' in skill_text
    assert 'tool_status_entrypoint: "scripts/status.py"' in skill_text
    assert 'tool_status_result_mode: "silent_ok"' in skill_text
    assert "request_id" in skill_text
    assert "REQ20260501000095" in skill_text
    assert "CHG20260413000011" in skill_text
    assert "Do not pass internal UUIDs" in skill_text
    assert "申请状态" in skill_text
    assert "是否审批通过" in skill_text
    assert "我刚才提交的申请是否已经被批准了" in skill_text
    assert "reuse the most recent `smartcmp_submit_request` Request ID" in skill_text
    assert "Treat the tool output as" in skill_text
    assert "current user's message language" in skill_text
    assert "`APPROVAL_PENDING`: not approved yet" in skill_text
    assert "do not claim approval or rejection" in skill_text


def test_approval_skill_does_not_claim_submitted_request_status_queries() -> None:
    skill_text = APPROVAL_SKILL.read_text(encoding="utf-8")

    assert "use smartcmp_get_request_status" in skill_text
    assert '  - "status"' not in skill_text
    assert "submitted request status" in skill_text


def test_approval_skill_separates_action_commands_from_detail_lookup() -> None:
    skill_text = APPROVAL_SKILL.read_text(encoding="utf-8")
    detail_keywords = skill_text.split("tool_detail_keywords:", 1)[1].split(
        "tool_detail_use_when:",
        1,
    )[0]
    detail_avoid_when = skill_text.split("tool_detail_avoid_when:", 1)[1].split(
        "tool_detail_groups:",
        1,
    )[0]

    assert "approve CHG20260413000011" in skill_text
    assert "agree RES20260505000010" in skill_text
    assert "pass TIC20260502000003" in skill_text
    assert "deny RES20260505000010" in skill_text
    assert "批准 CHG20260413000011" in skill_text
    assert "tool_approve_aliases:" in skill_text
    assert tool_metadata_contains(skill_text, "tool_approve_keywords:", "approve")
    assert tool_metadata_contains(skill_text, "tool_approve_keywords:", "agree")
    assert tool_metadata_contains(skill_text, "tool_approve_keywords:", "pass")
    assert tool_metadata_contains(skill_text, "tool_reject_keywords:", "deny")
    assert tool_metadata_contains(skill_text, "tool_reject_keywords:", "refuse")
    assert "use smartcmp_approve" in detail_avoid_when
    assert "use smartcmp_reject" in detail_avoid_when
    assert '  - "审批"' not in detail_keywords
    assert '  - "TIC"' not in detail_keywords


def test_request_skill_allows_structural_instruction_metadata_without_params() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "structural instruction metadata for the selected catalog" in skill_text
    assert "`node`, `type`, `osType`, or `cloudEntryTypeIds`" in skill_text


def test_request_skill_keeps_instruction_reasoning_anchored_to_current_service() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Any answer, follow-up, preview, or request-building step" in skill_text
    assert "must use only the currently selected" in skill_text
    assert "catalog/service" in skill_text
    assert "Do **NOT** switch to another service" in skill_text
    assert "generic VM defaults" in skill_text


def test_request_skill_defines_empty_instruction_metadata_fallback() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Empty Instruction Metadata Fallback" in skill_text
    assert "currently selected catalog has no" in skill_text
    assert "`instructions.parameters` list" in skill_text
    assert "fixed type-specific fields" in skill_text
    assert "not to reconstruct hidden service configuration" in skill_text
    assert "Do **NOT** infer missing fields from service name" in skill_text
    assert "Do **NOT** invent or ask for `templateId`, `logicTemplateName`, `networkId`" in skill_text
    assert "Before submit, never guess hidden fields" in skill_text


def test_request_skill_empty_instruction_compute_fallback_uses_compute_fields() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")
    fallback = skill_text.split("### Compute fallback", 1)[1].split(
        "### Non-Compute cloud fallback",
        1,
    )[0]

    assert '"cloudchef.nodes.Compute"' in fallback
    assert "`catalogId`" in fallback
    assert "`catalogName`" in fallback
    assert "`businessGroupId`" in fallback
    assert "`name`" in fallback
    assert "`description`" in fallback
    assert "`resourceBundleTags`" in fallback
    assert "`computeProfileId`" in fallback
    assert "`credentialUser`" in fallback
    assert "`credentialPassword`" in fallback
    assert "smartcmp_list_facets" in fallback
    assert "smartcmp_list_flavors" in fallback
    assert "flavor `id`" in fallback
    assert '"computeProfileId": "<flavor id from smartcmp_list_flavors>"' in fallback
    assert '"description": "<user-provided request description>"' in fallback
    assert "`templateId`" not in fallback
    assert "`networkId`" not in fallback
    assert "Never use example disk sizes as defaults" in fallback


def test_request_skill_empty_instruction_non_compute_fallback_collects_description_and_tags() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")
    fallback = skill_text.split("### Non-Compute cloud fallback", 1)[1].split(
        "### Ticket fallback",
        1,
    )[0]

    assert '`"GENERIC_SERVICE"`' in fallback
    assert "selected catalog `type` is present but not" in fallback
    assert '`"cloudchef.nodes.Compute"`' in fallback
    assert "`catalogId`" in fallback
    assert "`catalogName`" in fallback
    assert "`businessGroupId`" in fallback
    assert "`name`" in fallback
    assert "`description`" in fallback
    assert "`resourceBundleTags`" in fallback
    assert "`type`" in fallback
    assert "`node_type` set to the selected catalog `type`" in fallback
    assert '"description": "<user-provided request description>"' in fallback
    assert "Do not call `smartcmp_list_flavors`" in fallback
    assert "usernames, passwords, disk size, template, or network fields" in fallback


def test_request_skill_allows_top_level_description_for_non_ticket_requests() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")
    field_placement = skill_text.split("## Field Placement", 1)[1].split(
        "### Parameter Key Rule",
        1,
    )[0]

    assert "**FORBIDDEN top-level:**" in field_placement
    forbidden_line = field_placement.split("**FORBIDDEN top-level:**", 1)[1].split("\n", 1)[0]
    assert "`description`" not in forbidden_line
    assert (
        "`description` is allowed at top-level for all non-ticket cloud/resource"
        in field_placement
    )
    assert "`genericRequest.description`, not top-level `description`" in field_placement


def test_request_skill_empty_instruction_ticket_fallback_avoids_resource_collection() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")
    fallback = skill_text.split("### Ticket fallback", 1)[1].split("## Terminology Mapping", 1)[0]

    assert '`"GENERIC_SERVICE"`' in fallback
    assert "`genericRequest.description` only" in fallback
    assert "Do not collect resource bundle tags or" in fallback
    assert "compute flavors for ticket catalogs" in fallback


def tool_metadata_contains(skill_text: str, section: str, value: str) -> bool:
    """Return whether a frontmatter list section contains a literal string item."""
    body = skill_text.split(section, 1)[1].split("\n", 20)[1:]
    return any(line.strip() == f'- "{value}"' for line in body if line.startswith("  - "))
