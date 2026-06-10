# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import io
import json
import re
import sys
import unicodedata
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROVIDER_ROOT
    / "skills"
    / "form-designer-agent"
    / "scripts"
    / "prepare_request_form.py"
)


def run_script(argv: list[str]):
    module_name = "test_prepare_request_form_script_module"

    stdout = io.StringIO()
    stderr = io.StringIO()
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            spec.loader.exec_module(module)
            exit_code = int(module.main(argv) or 0)
    finally:
        sys.modules.pop(module_name, None)

    return exit_code, stdout.getvalue(), stderr.getvalue()


def extract_meta(stderr: str) -> dict:
    match = re.search(
        r"##REQUEST_FORM_META_START##\s*(\{.*?\})\s*##REQUEST_FORM_META_END##",
        stderr,
        re.S,
    )
    assert match, stderr
    return json.loads(match.group(1))


def test_prepare_request_form_returns_compact_schema_form_contract() -> None:
    instruction = "Create an extension attribute form for owner and cost center"

    exit_code, stdout, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert "[SUCCESS] Schema form preparation ready" in stdout
    assert meta["decision"] == "schema_form_definition_ready"
    assert meta["mode"] == "new"
    assert meta["instruction"] == instruction
    assert meta["sourceRequired"] is False
    assert meta["downloadAllowed"] is False
    assert meta["artifactAllowed"] is False
    assert meta["outputDeliveryContract"] == {
        "delivery": "chat_json_text_only",
        "fileOutputAllowed": False,
        "artifactOutputAllowed": False,
        "downloadOutputAllowed": False,
        "requiredFormat": "single_fenced_json_block",
    }
    assert meta["retention"] == "schema_form_json"
    assert meta["interactionSurface"] == "smartcmp_platform_service_model_form"
    assert meta["finalAction"] == "return_schema_form_json_only"
    assert meta["cmpWriteAllowed"] is False
    assert meta["cmpWriteRequiresSecondConfirmation"] is False
    assert "handoffSkill" not in meta
    assert "submitted" not in meta
    assert "writeAllowed" not in meta

    assert meta["backendParameterContract"]["shape"] == "kv_json_object"
    assert meta["backendParameterContract"]["sourcePolicy"] == "shape_dependent"
    assert meta["backendParameterContract"]["sourcesByShape"] == {
        "smartcmp_content": "content.model",
        "schema_only": "properties",
        "angular2_schema": "properties",
        "angular1_schema_form_model": "schema.properties and form[].key",
        "formio_components": "components[].key",
    }
    assert meta["backendParameterKeys"] == []
    assert meta["backendParameterPayloadPreview"] == {}

    output_contract = meta["designerOutputContract"]
    assert output_contract["primaryJson"] == "chat_fenced_json_value"
    assert output_contract["fencedBlockContent"] == "bare_json_value_not_wrapper"
    assert output_contract["forbiddenOutputWrappers"] == ["designerPasteJson"]
    assert output_contract["shapePolicy"] == "preserve_target_module_shape"
    assert output_contract["newFormDefaultShape"] == "schema_only"
    assert output_contract["schemaOnly"]["rootRequiredKeys"] == [
        "type",
        "properties",
        "required",
        "fieldsets",
        "widget",
    ]
    assert output_contract["schemaOnly"]["rootWidgetId"] == "object"
    assert output_contract["schemaOnly"]["fieldDefinitionLocation"] == "properties.<fieldKey>"
    assert output_contract["schemaOnly"]["fieldsetsLocation"] == "fieldsets"
    assert output_contract["schemaOnly"]["sentinel"]["key"] == "schemaFormValid"
    assert output_contract["schemaOnly"]["sentinel"]["property"]["widget"] == {"id": "hidden"}
    assert output_contract["schemaOnly"]["visibleFieldRequiredKeys"] == [
        "id",
        "type",
        "widget.id",
        "inputClass",
        "index",
        "title",
        "config.visibility.allowInRequest",
        "config.modification.allowInRequest",
    ]
    assert "templateOptions" in output_contract["schemaOnly"]["forbiddenFieldKeys"]
    assert "model/schema/options" in output_contract["schemaOnly"]["forbiddenNewRootShapes"]
    assert output_contract["completeConfigOnlyWhen"] == (
        "user_explicitly_requests_complete_config_or_source_already_uses_that_shape"
    )
    assert output_contract["fieldConfigLocation"] == "schema_or_root_properties.<fieldKey>"
    assert output_contract["optionsRole"] == "external_context_not_field_definitions"
    assert output_contract["supportedSourceShapes"] == [
        "smartcmp_content",
        "schema_only",
        "formio_components",
        "angular1_schema_form_model",
        "angular2_schema",
    ]

    assert meta["manualReference"] == {
        "sourcePageId": "123109820",
        "title": "Schema Form manual",
        "policy": "single_page_reference_do_not_crawl_child_pages",
    }
    assert meta["catalogPolicy"]["commonResourceRequestFields"] == [
        "department",
        "project",
        "owner",
        "name",
    ]
    assert meta["catalogPolicy"]["catalogLookupRequiredFor"] == "catalog_specific_dynamic_fields_only"
    assert meta["catalogPolicy"]["commonFieldsDynamicInRequestPage"] is True
    assert meta["catalogPolicy"]["commonFieldInputPolicy"] == (
        "context_only_no_generated_inputs_unless_explicit_visible_source_fields"
    )
    assert meta["catalogPolicy"]["commonFieldRuntimeEvidence"] == (
        "request-page bindings and submit payload keys verified from SmartCMP runtime"
    )
    assert meta["catalogPolicy"]["fixedNoCatalogLookup"] == [
        "department",
        "project",
        "owner",
        "name",
    ]
    assert meta["catalogPolicy"]["fixedCatalogToolsForbidden"] is True
    assert meta["catalogPolicy"]["fixedRequestFieldKeys"] == {
        "department": {
            "requestPageModel": "vm.deploymentObj.businessGroupId",
            "catalogFormSourceParam": "sourceConfigParamter.businessGroupId",
            "submitPayloadKey": "businessGroupId",
        },
        "project": {
            "requestPageModel": "vm.selectedGroup",
            "catalogFormSourceParam": "sourceConfigParamter.projectId",
            "submitPayloadKey": "projectId",
        },
        "owner": {
            "requestPageModel": "vm.selectedUser.id",
            "catalogFormSourceParam": "sourceConfigParamter.ownerId",
            "submitPayloadKey": "ownerId",
        },
        "name": {
            "requestPageModel": "vm.deploymentObj.name",
            "catalogFormSourceParam": None,
            "submitPayloadKey": "name",
            "note": "name is not passed into catalog-form sourceConfigParamter",
        },
    }
    assert meta["catalogPolicy"]["commonFieldRuntimeLocatorHint"] == (
        "department=sourceConfigParamter.businessGroupId|payload.businessGroupId;"
        "project=sourceConfigParamter.projectId|payload.projectId;"
        "owner=sourceConfigParamter.ownerId|payload.ownerId;"
        "name=payload.name|vm.deploymentObj.name|dom_not_sourceConfigParamter"
    )
    assert meta["catalogPolicy"]["userEnteredCatalogSpecificFieldsRequireCatalog"] is False
    assert meta["catalogPolicy"]["askCatalogOnlyWhen"] == (
        "field_must_be_dynamic_from_catalog_context_and_is_not_common_request_field"
    )
    assert meta["catalogPolicy"]["exampleUserEnteredSpecialFields"] == [
        "cpu_core_count",
        "ip_address",
        "environment_note",
    ]
    assert meta["dynamicFieldPolicy"]["functionLocations"] == [
        "config.changeEvent",
        "config.value.customFunction",
        "config.value.expression",
    ]
    assert "function(itemId, schema, model, sourceParams)" in meta["dynamicFieldPolicy"]["changeEventSignature"]
    assert meta["dynamicFieldPolicy"]["hookLocation"] == (
        "properties.<fieldKey>.config.changeEvent or "
        "schema.properties.<fieldKey>.config.changeEvent"
    )
    assert meta["dynamicFieldPolicy"]["modelArgument"] == "third_argument_model"
    assert meta["dynamicFieldPolicy"]["sourceParamsArgument"] == "fourth_argument_sourceParams"
    assert meta["dynamicFieldPolicy"]["onePhysicalLine"] is True
    assert meta["dynamicFieldPolicy"]["forbidRootLevelChangeEvent"] is True
    assert meta["dynamicFieldPolicy"]["forbidOptionsFieldsFieldConfig"] is True
    assert meta["dynamicFieldPolicy"]["forbiddenPseudoDslKeys"] == [
        "computed_values",
        "root-level expression",
        "concat(...)",
        "context.project",
        "context.owner",
    ]
    assert meta["dynamicFieldPolicy"]["patternSource"] == "successful_existing_form_scripts"
    assert meta["dynamicFieldPolicy"]["refreshTriggerPolicy"] == (
        "visible_non_common_string_trigger_no_hidden_return_dispatch"
    )
    assert meta["dynamicFieldPolicy"]["defaultRuntimeHook"] == "config.changeEvent"
    assert meta["dynamicFieldPolicy"]["autoRequestContextSyncHook"] == (
        "config.value.source=mock;method=mock;expression=function(...)"
    )
    assert meta["dynamicFieldPolicy"]["valueExpressionSignature"] == (
        "function(model,sourceParams,schema,...)"
    )
    assert meta["dynamicFieldPolicy"]["autoRequestContextSyncPolicy"] == (
        "mock_timer_guarded"
    )
    assert meta["dynamicFieldPolicy"]["fixedContextWatcher"] is True
    assert meta["dynamicFieldPolicy"]["contextResolution"] == (
        "scope_api_dom_cache_guard"
    )
    assert meta["dynamicFieldPolicy"]["retainLastNonEmptyContextValues"] is True
    assert meta["dynamicFieldPolicy"]["emptyContextWriteGuard"] is True
    assert meta["dynamicFieldPolicy"]["modelValueGuard"] is True
    assert meta["dynamicFieldPolicy"]["dispatchThrottle"] is True
    assert meta["dynamicFieldPolicy"]["compileFunctionStrings"] is True
    assert meta["dynamicFieldPolicy"]["malformedTryForbidden"] is True
    assert meta["dynamicFieldPolicy"]["customFunctionPolicy"] == (
        "only_when_existing_source_proves_renderer_executes_it"
    )
    assert meta["dynamicFieldPolicy"]["emptyContextTemplatePolicy"] == "forbid_empty_common_templates"
    assert meta["jsonValidationPolicy"] == {
        "mustReturnParseableJson": True,
        "validateBeforeReturn": "JSON.parse",
        "fieldDefinitionsStayInProperties": True,
        "validatorTool": "smartcmp_validate_request_form_json",
    }
    assert meta["formLifecyclePolicy"] == {
        "newForm": "generate_from_user_requirements",
        "existingFormUrl": "call_smartcmp_fetch_request_form_source",
        "existingFormJson": "preserve_shape_and_modify_requested_parts",
        "cmpWriteAllowed": False,
        "delivery": "chat_only",
    }
    assert len(meta["nextStep"]) <= 1400
    assert "Schema Form JSON" in meta["nextStep"]
    assert "Return the generated JSON as chat text in one fenced json code block" in meta["nextStep"]
    assert "save, mount, publish, or submit" in meta["nextStep"]
    assert "user-filled special fields do not need catalog lookup" in meta["nextStep"].lower()
    assert "customFunction also assigns model[backendKey]" in meta["nextStep"]
    assert "mock expression watcher" in meta["nextStep"]
    assert "never sourceParams.name/raw ownerId/vm/jq/one-shot timer" in meta["nextStep"]
    assert "retain last non-empty context values" in meta["nextStep"]
    assert "no empty writes" in meta["nextStep"]
    assert "model guard" in meta["nextStep"]
    assert "dispatch throttle" in meta["nextStep"]
    assert "default hidden-submitted" in meta["nextStep"]
    assert "source fields only when explicit" in meta["nextStep"]
    assert "preserve business group label" in meta["nextStep"]
    assert "never model.name/model.owner" in meta["nextStep"]
    assert "empty common context templates" in meta["nextStep"]
    assert "default hook is config.changeEvent" in meta["nextStep"]
    assert "run smartcmp_validate_request_form_json" in meta["nextStep"]
    assert "Validate the final JSON with JSON.parse" in meta["nextStep"]
    assert "compile JS" in meta["nextStep"]
    assert "full manual" not in meta["nextStep"].lower()
    assert "COMMON_RESOURCE_REQUEST_FIELD_POLICY" not in stderr


def test_prepare_request_form_new_forms_are_schema_only_preview_json() -> None:
    exit_code, stdout, stderr = run_script(
        ["Create a service catalog form for cost center, owner login, and project code"]
    )

    meta = extract_meta(stderr)

    assert exit_code == 0
    assert "[SUCCESS] Schema form preparation ready" in stdout
    assert meta["designerPasteShape"] == "schema_only"
    assert meta["previewCompatible"] is True
    assert meta["designerOutputContract"]["newFormDefaultShape"] == "schema_only"
    assert meta["designerOutputContract"]["schemaOnly"]["sentinel"]["includeInFieldsets"] is True
    assert meta["designerOutputContract"]["schemaOnly"]["jsonMustParseBeforeReturn"] is True
    assert "schema-only" in meta["nextStep"]
    assert "user-requested fields" in meta["nextStep"]


def test_prepare_request_form_meta_stays_small() -> None:
    exit_code, _, stderr = run_script(["Create a request form for project and owner"])

    meta = extract_meta(stderr)
    encoded = json.dumps(meta, ensure_ascii=False)
    assert exit_code == 0
    assert len(encoded) < 7500
    assert len(meta["nextStep"]) < 1400
    assert "ownerDisplayResolutionOrder" not in encoded
    assert "businessGroupDisplayNameResolution" not in encoded
    assert "sourceConfigParamter.projectId" in encoded
    assert "sourceConfigParamter.ownerId" in encoded
    assert "project=projects|projectName|projectIds" not in encoded
    assert "ownerText=owners|ownerName|ownerDisplayName" not in encoded


def test_prepare_request_form_special_user_entered_fields_do_not_need_catalog_context() -> None:
    exit_code, _, stderr = run_script(
        ["Create a form with user-entered CPU cores and a dynamic owner display"]
    )

    meta = extract_meta(stderr)
    policy = meta["catalogPolicy"]

    assert exit_code == 0
    assert policy["commonFieldsDynamicInRequestPage"] is True
    assert policy["userEnteredCatalogSpecificFieldsRequireCatalog"] is False
    assert "owner" in policy["commonResourceRequestFields"]
    assert policy["fixedNoCatalogLookup"] == [
        "department",
        "project",
        "owner",
        "name",
    ]
    assert policy["fixedCatalogToolsForbidden"] is True
    assert policy["catalogLookupRequiredFor"] == "catalog_specific_dynamic_fields_only"


def test_prepare_request_form_requires_catalog_lookup_for_named_catalog_dynamic_fields() -> None:
    instruction = (
        "Create a service catalog form for IP request named test-ip. "
        "infoblox_ip_attr is built from application system and owner."
    )

    exit_code, stdout, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    gate = meta["catalogLookupGate"]
    assert exit_code == 0
    assert "[SUCCESS] Schema form preparation ready" in stdout
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert meta["finalAction"] == "call_catalog_lookup_before_json"
    assert gate["requiredBeforeJson"] is True
    assert gate["reason"] == "named_service_catalog_dynamic_fields"
    assert gate["firstTool"] == "smartcmp_form_designer_list_services"
    assert gate["detailTool"] == "smartcmp_form_designer_get_catalog_detail"
    assert gate["resolverTool"] == "smartcmp_form_designer_resolve_catalog_fields"
    assert gate["afterKeysResolvedTool"] == "smartcmp_generate_catalog_context_form"
    assert "Request Parameter Instructions" in gate["evidenceRequired"]
    assert "label=key" in gate["nextStep"]
    assert "resolve requested labels" in gate["nextStep"].lower()
    assert "do not generate json before catalog lookup" in meta["nextStep"].lower()
    assert "smartcmp_form_designer_resolve_catalog_fields" in meta["nextStep"]


def test_prepare_request_form_json_like_template_requires_catalog_lookup_without_compose_words() -> None:
    instruction = (
        "Create a form for EIP named test-eip. The form has only one backend field named mixture. "
        "mixture is {billing type: billing type value, bandwidth: bandwidth value}."
    )

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert meta["catalogLookupGate"]["requiredBeforeJson"] is True


def test_prepare_request_form_avoids_large_language_trigger_alias_tables() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "SEMANTIC_ALIASES" not in script
    assert "COMPOSE_OPERATION_MARKERS" not in script
    assert "\\u" not in script
    assert not any("CJK UNIFIED" in unicodedata.name(ch, "") for ch in script)


def test_prepare_request_form_catalog_composed_only_keeps_one_backend_field() -> None:
    instruction = (
        "Create a form for EIP named test-eip. The form has only one backend field named mixture. "
        "mixture value is built from billing type and bandwidth."
    )

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    gate = meta["catalogLookupGate"]
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert gate["requiredBeforeJson"] is True
    assert gate["composedFieldShape"] == "single_requested_backend_field_only"
    assert gate["composedSubmitFieldVisibility"] == "hidden_by_default_runtime_offscreen"
    assert "do not create visible source fields" in gate["sourceFieldPolicy"]
    assert "hidden submitted composed backend field" in gate["nextStep"]


def test_prepare_request_form_catalog_composed_template_keeps_one_backend_field() -> None:
    instruction = (
        "Create a form for EIP named test-eip. The form has only one backend field named mixture. "
        "mixture is {billing type: billing type value, bandwidth: bandwidth value}."
    )

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    gate = meta["catalogLookupGate"]
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert gate["requiredBeforeJson"] is True
    assert gate["composedFieldShape"] == "single_requested_backend_field_only"
    assert gate["composedSubmitFieldVisibility"] == "hidden_by_default_runtime_offscreen"
    assert "hidden submitted composed backend field" in gate["nextStep"]


def test_prepare_request_form_catalog_composed_intent_uses_value_structure() -> None:
    instructions = [
        (
            "Create a form for EIP named test-eip. The form has only one backend field named mixture. "
            "mixture value is built from billing type and bandwidth."
        ),
        (
            "Create a form for EIP named test-eip. The form has only one backend field named mixture. "
            "mixture value comes from billing type and bandwidth."
        ),
        (
            "Create a form for EIP named test-eip. The form has only one backend field named mixture. "
            "mixture takes billing type and bandwidth as value."
        ),
    ]

    for instruction in instructions:
        exit_code, _, stderr = run_script([instruction])

        meta = extract_meta(stderr)
        assert exit_code == 0
        assert meta["decision"] == "catalog_lookup_required_before_form_json"
        assert meta["catalogLookupGate"]["requiredBeforeJson"] is True


def test_prepare_request_form_named_catalog_does_not_require_service_catalog_words() -> None:
    instruction = (
        "Create a form for RDS named test-rds. The form has only one backend field named mixture. "
        "mixture is {billing type: billing type value, storage size: storage size value}."
    )

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert meta["catalogLookupGate"]["requiredBeforeJson"] is True


def test_prepare_request_form_named_catalog_creation_words_require_catalog_lookup() -> None:
    instructions = [
        (
            "Please create a form for EIP named test-eip. The form has only one backend field named mixture. "
            "mixture value is built from billing type and bandwidth."
        ),
        (
            "Build a form for EIP named test-eip. "
            "mixture is {billing type: billing type value, bandwidth: bandwidth value}."
        ),
    ]

    for instruction in instructions:
        exit_code, _, stderr = run_script([instruction])

        meta = extract_meta(stderr)
        assert exit_code == 0
        assert meta["decision"] == "catalog_lookup_required_before_form_json"
        assert meta["catalogLookupGate"]["requiredBeforeJson"] is True


def test_prepare_request_form_does_not_catalog_gate_non_catalog_named_form_targets() -> None:
    instruction = "Create an approval-flow form. summary value is composed from priority and note."

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "schema_form_definition_ready"
    assert "catalogLookupGate" not in meta


def test_prepare_request_form_does_not_catalog_gate_named_catalog_custom_user_fields() -> None:
    instructions = [
        "Create a form for EIP with only one field priority.",
        "Create a form for EIP with only one user-entered priority field.",
    ]

    for instruction in instructions:
        exit_code, _, stderr = run_script([instruction])

        meta = extract_meta(stderr)
        assert exit_code == 0
        assert meta["decision"] == "schema_form_definition_ready"
        assert "catalogLookupGate" not in meta


def test_prepare_request_form_catalog_lookup_gate_is_not_tied_to_known_catalog_field_names() -> None:
    instruction = (
        "Create a service catalog form for new resource approval named test-new. "
        "summary_attr is built from cost allocation and security level; both values come from this service catalog."
    )

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert meta["catalogLookupGate"]["requiredBeforeJson"] is True


def test_prepare_request_form_does_not_catalog_gate_fixed_request_context_fields() -> None:
    instruction = "Create a service catalog form. backend_test is built from name and owner."

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "schema_form_definition_ready"
    assert "catalogLookupGate" not in meta


def test_prepare_request_form_requires_catalog_gate_for_noncommon_dynamic_request_fields() -> None:
    instruction = "Create a service catalog form that fetches description, quantity, and execution time."

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert meta["catalogLookupGate"]["requiredBeforeJson"] is True
    assert meta["catalogPolicy"]["commonFieldsRequireCatalogLookup"] is False


def test_prepare_request_form_requires_catalog_gate_for_mixed_common_and_noncommon_dynamic_fields() -> None:
    instruction = "Create a service catalog form that fetches name and CPU core count."

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert meta["catalogLookupGate"]["requiredBeforeJson"] is True


def test_prepare_request_form_rejects_empty_instruction() -> None:
    exit_code, stdout, stderr = run_script(["  "])

    assert exit_code == 1
    assert "[ERROR] Missing required instruction argument." in stdout
    assert "REQUEST_FORM_META" not in stderr
