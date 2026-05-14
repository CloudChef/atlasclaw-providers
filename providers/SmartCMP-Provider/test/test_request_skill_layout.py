# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
REQUEST_SKILL = PROVIDER_ROOT / "skills" / "request" / "SKILL.md"
APPROVAL_SKILL = PROVIDER_ROOT / "skills" / "approval" / "SKILL.md"
DECOMPOSITION_SKILL = PROVIDER_ROOT / "skills" / "request-decomposition-agent" / "SKILL.md"
DECOMPOSITION_GUIDELINES = (
    PROVIDER_ROOT
    / "skills"
    / "request-decomposition-agent"
    / "references"
    / "decomposition-guidelines.md"
)


def test_request_skill_requires_business_group_resolution() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "smartcmp_list_available_bgs" in skill_text
    assert "Business-Group Resolution" in skill_text
    assert "Steps 1 and 2 are mandatory" in skill_text
    assert "Never ask the user to type a" in skill_text
    assert "If multiple groups remain, ask one concise numbered question" in skill_text
    assert "Do not display business group UUIDs" in skill_text
    assert "ask for both in the same sentence" in skill_text
    assert "Use the selected business group's `id` as top-level `businessGroupId`" in skill_text


def test_request_skill_handles_business_group_selection_turns() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "previous assistant message asked the user to choose a business group" in skill_text
    assert "bare number or group name" in skill_text
    assert "never as an unsupported operation" in skill_text
    assert "`smartcmp_list_available_bgs` again with the same selected catalog UUID" in skill_text
    assert "resolve the user's selection" in skill_text
    assert "against that" in skill_text
    assert "may be called one extra time only" in skill_text


def test_request_skill_resolves_service_numbers_to_catalog_uuid() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Catalog identity contract" in skill_text
    assert "Displayed service list numbers are conversation choices only" in skill_text
    assert "latest `smartcmp_list_services` result" in skill_text
    assert "`catalogId` must be the selected catalog metadata UUID" in skill_text
    assert "never the displayed" in skill_text
    assert "never `sourceKey`" in skill_text
    assert "There is no catalog questionnaire/default-property/preview tool" in skill_text


def test_request_skill_uses_generated_markdown_only() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Generated Markdown Instructions" in skill_text
    assert "`instructions.resourceSpecs`" in skill_text
    assert "`instructions.topLevelFields`" in skill_text
    assert "`instructions.params`" in skill_text
    assert "Ignore old JSON instruction payloads" in skill_text
    assert "Do not use `instructions.parameters`" in skill_text
    assert "preview.py" not in skill_text
    assert "smartcmp_preview_request" not in skill_text
    assert "Empty Instruction Metadata Fallback" not in skill_text
    assert "Runtime Default Guard" not in skill_text


def test_request_skill_limits_markdown_body_to_request_instructions() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Instruction section boundary" in skill_text
    assert "`# Request Parameter Instructions`: YAML parameter contract" in skill_text
    assert "only `# Request Parameter Instructions` and `# Request Instructions` are in" in skill_text
    assert "Read `# Request Parameter Instructions` first" in skill_text
    assert "`instructions.requestInstructions` from exactly `# Request Instructions`" in skill_text
    assert "The `# Request Instructions` section is optional" in skill_text
    assert "If it is absent, use" in skill_text
    assert "Stop reading request instructions at the next same-level heading" in skill_text
    assert "`# Preapproval Instructions`" in skill_text
    assert "Never fall through to `# Preapproval Instructions`" in skill_text
    assert "Ignore all other sections for request building" in skill_text
    assert "must not change required" in skill_text
    assert "has no request-body" in skill_text


def test_request_skill_defines_markdown_request_assembly() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Top-level JSON always includes `catalogId`, `catalogName`" in skill_text
    assert "`businessGroupId`, and `name`" in skill_text
    assert "Generated field attributes belong in `# Request Parameter Instructions`" in skill_text
    assert "If an active field declares static `options`" in skill_text
    assert "Do not add a second field-property list" in skill_text
    assert "Treat the body as" in skill_text
    assert "`topLevelFields.name.ask: true`" in skill_text
    assert "Do not auto-generate it" in skill_text
    assert "Do not include `userLoginId`" in skill_text
    assert "root request fields declared in `instructions.params.<key>`" in skill_text
    assert "top-level JSON object `params.<key>`" in skill_text
    assert "Do not put root `instructions.params` fields into" in skill_text
    assert "`instructions.genericRequest.description`" in skill_text
    assert "`genericRequest.description`" in skill_text
    assert "`instructions.genericRequest.processForm.<key>`" in skill_text
    assert "`genericRequest.processForm.<key>`" in skill_text
    assert "field schemas declared directly on `instructions.resourceSpecs[]`" in skill_text
    assert "directly on the same `resourceSpecs[]` item" in skill_text
    assert "Do not create or consume a literal `fields` object" in skill_text
    assert "`resourceSpecs[].resourceBundleId`" in skill_text
    assert "smartcmp_list_resource_bundles" in skill_text
    assert "Put `resourceBundleTags` at the same level as `resourceBundleId`" in skill_text
    assert "`smartcmp_list_facets` after" in skill_text
    assert "`resourceSpecs[].resourceBundleTags`" in skill_text
    assert '`["<facet.key>:<option.key>"]`' in skill_text
    assert "`resourceBundleTags` and `resourceBundleId` are mutually exclusive" in skill_text
    assert "If both are declared and active, use" in skill_text
    assert "call `smartcmp_list_resource_bundles` after" in skill_text
    assert "component_type" in skill_text
    assert "node_type" in skill_text
    assert "resourceSpecs[].componentType" not in skill_text
    assert "`resourceSpecs[].resourceBundleParams.<key>`" in skill_text
    assert "`resourceBundleParams` is only for defaulted resource-pool placement fields" in skill_text
    assert "Do not ask" in skill_text
    assert "missing `resourceBundleParams`" in skill_text
    assert "network configuration fields must be under" in skill_text
    assert "`resourceSpecs[].params.<key>`" in skill_text
    assert "External API lookup fields" in skill_text
    assert "direct Compute lookup fields" in skill_text
    assert "without a default, omit it" in skill_text
    assert "Use `defaultValue` / `default_value` silently" in skill_text
    assert "When an active field has static `options`" in skill_text
    assert "collecting remaining fields or showing the" in skill_text
    assert "This applies even when the field has a default" in skill_text
    assert "可选：internet=公网，intranet=私网" in skill_text
    assert "Do not ask the user whether to" in skill_text
    assert "Never serialize metadata keys" in skill_text
    assert "`options`" in skill_text
    assert '"<directResourceSpecKey>": "<active value>"' in skill_text
    assert "Ticket/work-order generated Markdown request shape" in skill_text
    assert '"genericRequest": {' in skill_text
    assert '"processForm": {' in skill_text


def test_request_skill_uses_resource_pool_chinese_term() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "always call SmartCMP resource pools `资源池`" in skill_text
    assert "Never call them `资源包`" in skill_text
    assert "resource pools from SmartCMP" in skill_text
    assert "resourceBundleId" in skill_text


def test_request_skill_defines_when_rules_for_markdown_fields() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Evaluate `when` before asking or serializing" in skill_text
    assert "If `when` is false, the field is inactive" in skill_text
    assert "`AddressType == intranet` means" in skill_text
    assert "Boolean values use `true` and `false`" in skill_text
    assert "re-evaluate dependent `when` fields" in skill_text


def test_request_skill_defines_resource_bundle_lookup() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert 'tool_resource_bundles_name: "smartcmp_list_resource_bundles"' in skill_text
    assert 'tool_resource_bundles_entrypoint: "scripts/list_resource_bundles.py"' in skill_text
    assert "generated Markdown declares" in skill_text
    assert "an active `resourceBundleId` field without a default" in skill_text
    assert "no active" in skill_text
    assert "`resourceBundleTags` field" in skill_text
    assert "strategy=RB_POLICY_STATIC" in skill_text
    assert "enabled=true" in skill_text
    assert "readOnly=false" in skill_text


def test_request_skill_constrains_facet_lookup_results() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert 'tool_facets_result_mode: "silent_ok"' in skill_text
    assert "Facet lookup result handling" in skill_text
    assert "Do not call `smartcmp_list_components`" in skill_text
    assert "Do not display raw facet records" in skill_text
    assert "Use the compact `FACET_META` data" in skill_text
    assert "If the user already supplied a tag/environment word" in skill_text
    assert "ask one concise numbered question" in skill_text
    assert "`resourceSpecs[].resourceBundleTags`" in skill_text


def test_request_skill_defines_missing_markdown_behavior() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Missing Markdown" in skill_text
    assert "Compute fallback only when" in skill_text
    assert "missing generated Markdown instructions" in skill_text
    assert "legacy Linux VM / Windows VM catalogs usable" in skill_text
    assert 'type: "cloudchef.nodes.Compute"' in skill_text
    assert "Call `smartcmp_list_flavors` when the user supplied a spec such as `2c4g`" in skill_text
    assert '"computeProfileId": "<flavor id>"' in skill_text
    assert 'serviceCategory: "GENERIC_SERVICE"' in skill_text
    assert "generated `instructions.genericRequest` Markdown" in skill_text
    assert '"genericRequest"' in skill_text
    assert "description" in skill_text


def test_request_skill_declares_provider_driven_workflow_metadata() -> None:
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
    assert "REQ20260501000095" in skill_text
    assert "CHG20260413000011" in skill_text
    assert "Do not pass internal UUIDs" in skill_text
    assert "reuse the most recent `smartcmp_submit_request` Request ID" in skill_text
    assert "current user's message language" in skill_text
    assert "`APPROVAL_PENDING`: not approved yet" in skill_text


def test_request_skill_defers_multi_vm_requests_to_decomposition_agent() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "Multi-resource routing boundary" in skill_text
    assert "one CMP request flow at a time" in skill_text
    assert "multiple resource types in one ask" in skill_text
    assert 'per-instance differences such as "first ..., second ..., third ..."' in skill_text
    assert "different specs per instance" in skill_text
    assert "do not continue with the single-catalog parameter" in skill_text


def test_request_decomposition_skill_covers_multi_vm_chat_phrases() -> None:
    skill_text = DECOMPOSITION_SKILL.read_text(encoding="utf-8")

    assert "mixed resource request" in skill_text
    assert "per-instance configuration differences" in skill_text
    assert "ordinal instance differences" in skill_text
    assert "distinct per-item configuration" in skill_text
    assert "For ordinary chat/runtime routing" in skill_text
    assert "first / second / third" in skill_text
    assert "differently configured component" in skill_text


def test_request_skill_explicitly_allows_same_type_quantity_requests() -> None:
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "multiple instances of the same resource type under one service request" in skill_text
    assert "Request multiple Linux virtual machines with the same specification" in skill_text
    assert "one service catalog / one resource type / one shared parameter set" in skill_text
    assert "Quantity by itself is **not** a decomposition signal." in skill_text
    assert "Single-instance vs shared-quantity contract" in skill_text
    assert "selected catalog schema" in skill_text
    assert "Do not\n  choose from a fixed alias list" in skill_text
    assert "fallback top-level `quantity`" in skill_text
    assert "multiple `instructions.resourceSpecs`" in skill_text


def test_request_decomposition_skill_excludes_same_type_quantity_only_requests() -> None:
    skill_text = DECOMPOSITION_SKILL.read_text(encoding="utf-8")
    guidelines_text = DECOMPOSITION_GUIDELINES.read_text(encoding="utf-8")

    assert "multiple resource types that should become separate CMP requests" in skill_text
    assert "same parameters in one request flow (use request skill)" in skill_text
    assert "Do **not** route" in skill_text
    assert "quantity N of the same resource type" in skill_text
    assert "Not A Decomposition Signal By Itself" in guidelines_text
    assert "Quantity alone for one resource type is not enough." in guidelines_text



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


def tool_metadata_contains(skill_text: str, section: str, value: str) -> bool:
    try:
        body = skill_text.split(section, 1)[1]
    except IndexError:
        return False

    next_tool_marker = body.find("\ntool_")
    if next_tool_marker != -1:
        body = body[:next_tool_marker]

    return f'"{value}"' in body


def test_request_decomposition_skill_requires_clarification_for_conflicting_ordinals() -> None:
    skill_text = DECOMPOSITION_SKILL.read_text(encoding="utf-8")

    assert 'Treat ordinal references such as "first", "second", "third", "fifth", or' in skill_text
    assert "If the stated instance quantity conflicts with the referenced ordinal" in skill_text
    assert "positions, stop and ask a focused clarification question" in skill_text
    assert '"request 4 instances, second ..., fifth ..., sixth ..."' in skill_text
    assert "do not guess the missing instance count" in skill_text
    assert "Ask for clarification before decomposition" in skill_text


def test_request_decomposition_guidelines_require_ordinal_quantity_validation() -> None:
    guidelines_text = DECOMPOSITION_GUIDELINES.read_text(encoding="utf-8")

    assert "Ordinal And Quantity Validation" in guidelines_text
    assert "If the user gives a total instance count and also gives ordinal per-item details" in guidelines_text
    assert "If the numbering is non-consecutive or out of range" in guidelines_text
    assert "Do not silently renumber the user's intent." in guidelines_text
    assert "Do not invent missing instances just to make the numbering contiguous." in guidelines_text
    assert "Instance quantity conflicts with the user's ordinal references." in guidelines_text
