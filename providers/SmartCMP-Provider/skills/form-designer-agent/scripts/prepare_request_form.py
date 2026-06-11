# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Prepare compact, read-only metadata for SmartCMP Schema Form generation."""

from __future__ import annotations

import json
import re
import sys
import unicodedata

BACKEND_PARAMETER_CONTRACT = {
    "shape": "kv_json_object",
    "sourcePolicy": "shape_dependent",
    "sourcesByShape": {
        "smartcmp_content": "content.model",
        "schema_only": "properties",
        "angular2_schema": "properties",
        "angular1_schema_form_model": "schema.properties and form[].key",
        "formio_components": "components[].key",
    },
}
OUTPUT_DELIVERY_CONTRACT = {
    "delivery": "chat_json_text_only",
    "fileOutputAllowed": False,
    "artifactOutputAllowed": False,
    "downloadOutputAllowed": False,
    "localFileOutputAllowed": False,
    "workspaceWriteAllowedForGeneratedJson": False,
    "mustInlineCompleteJsonTextInChat": True,
    "forbiddenDeliveryMethods": [
        "local_file_path",
        "workspace_artifact",
        "download_link",
        "attachment",
        "partial_json_plus_file_reference",
    ],
    "requiredFormat": "single_fenced_json_block",
}
SCHEMA_ONLY_CONTRACT = {
    "rootRequiredKeys": ["type", "properties", "required", "fieldsets", "widget"],
    "rootWidgetId": "object",
    "fieldDefinitionLocation": "properties.<fieldKey>",
    "fieldsetsLocation": "fieldsets",
    "sentinel": {
        "key": "schemaFormValid",
        "property": {
            "hidden": True,
            "type": "boolean",
            "default": True,
            "condition": "1 === 2",
            "widget": {"id": "hidden"},
        },
        "includeInFieldsets": True,
    },
    "visibleFieldRequiredKeys": ["id", "type", "widget.id", "inputClass", "index", "title", "config.visibility.allowInRequest", "config.modification.allowInRequest"],
    "forbiddenFieldKeys": ["templateOptions", "formlyConfig", "widget.type", "widget.formlyConfig"],
    "forbiddenNewRootShapes": ["model/schema/options", "content", "components", "fields", "layout", "form"],
    "jsonMustParseBeforeReturn": True,
}
DESIGNER_OUTPUT_CONTRACT = {
    "primaryJson": "chat_fenced_json_value",
    "fencedBlockContent": "bare_json_value_not_wrapper",
    "forbiddenOutputWrappers": ["designerPasteJson"],
    "shapePolicy": "preserve_target_module_shape",
    "newFormDefaultShape": "schema_only",
    "schemaOnly": SCHEMA_ONLY_CONTRACT,
    "completeConfigOnlyWhen": (
        "user_explicitly_requests_complete_config_or_source_already_uses_that_shape"
    ),
    "fieldConfigLocation": "schema_or_root_properties.<fieldKey>",
    "optionsRole": "external_context_not_field_definitions",
    "supportedSourceShapes": [
        "smartcmp_content",
        "schema_only",
        "formio_components",
        "angular1_schema_form_model",
        "angular2_schema",
    ],
    "forceModelSchemaOptions": False,
    "expertModePreviewDefault": "schema_only",
}
CATALOG_POLICY = {
    "serviceCatalogFieldPolicy": "user must specify the target service catalog before any service-catalog field is read",
    "fixedRequestContextFields": [],
    "fixedNoCatalogLookup": [],
    "fixedCatalogToolsForbidden": False,
    "commonFieldsRequireCatalogLookup": True,
    "userEnteredCatalogSpecificFieldsRequireCatalog": False,
    "catalogLookupRequiredFor": "all_service_catalog_dynamic_fields",
    "askCatalogOnlyWhen": "field_must_be_dynamic_from_service_catalog_context",
    "catalogUrlWithUuidTool": "smartcmp_form_designer_get_catalog_detail",
    "catalogNameTool": "smartcmp_form_designer_list_services",
    "catalogDetailEvidence": "Request Parameter Instructions",
    "exampleUserEnteredSpecialFields": ["cpu_core_count", "ip_address", "environment_note"],
}
CATALOG_REFERENCE_MARKERS = ("catalog-ui/request", "service catalog")
DYNAMIC_FIELD_POLICY = {
    "patternSource": "successful_existing_form_scripts",
    "functionLocations": ["config.changeEvent", "config.value.customFunction", "config.value.expression"],
    "defaultRuntimeHook": "config.changeEvent",
    "customFunctionPolicy": "only_when_existing_source_proves_renderer_executes_it",
    "autoCatalogContextSyncHook": "config.value.source=mock;method=mock;expression=function(...)",
    "valueExpressionSignature": "function(model,sourceParams,schema,...)",
    "autoCatalogContextSyncPolicy": "mock_timer_guarded",
    "contextResolution": "catalog_detail_key_scope_dom_cache_guard",
    "retainLastNonEmptyCatalogValues": True,
    "emptyContextWriteGuard": True,
    "modelValueGuard": True,
    "dispatchThrottle": True,
    "compileFunctionStrings": True,
    "malformedTryForbidden": True,
    "hookLocation": "properties.<fieldKey>.config.changeEvent or schema.properties.<fieldKey>.config.changeEvent",
    "changeEventSignature": "function(itemId, schema, model, sourceParams)",
    "modelArgument": "third_argument_model",
    "sourceParamsArgument": "fourth_argument_sourceParams",
    "mustAssignSubmittedModelKey": "model[backendKey] = value",
    "onePhysicalLine": True,
    "forbidPlaceholderDefaults": True,
    "forbidRootLevelChangeEvent": True,
    "forbidOptionsFieldsFieldConfig": True,
    "forbiddenPseudoDslKeys": [
        "computed_values",
        "root-level expression",
        "concat(...)",
        "context.project",
        "context.owner",
    ],
    "refreshTriggerPolicy": "visible_non_common_string_trigger_no_hidden_return_dispatch",
    "emptyContextTemplatePolicy": "forbid_empty_catalog_templates",
}
MANUAL_REFERENCE = {
    "sourcePageId": "123109820",
    "title": "Schema Form manual",
    "policy": "single_page_reference_do_not_crawl_child_pages",
}

JSON_VALIDATION_POLICY = {
    "mustReturnParseableJson": True,
    "validateBeforeReturn": "JSON.parse",
    "fieldDefinitionsStayInProperties": True,
    "validatorTool": "smartcmp_validate_request_form_json",
}

FORM_LIFECYCLE_POLICY = {
    "newForm": "generate_from_user_requirements",
    "existingFormUrl": "call_smartcmp_fetch_request_form_source",
    "existingFormJson": "preserve_shape_and_modify_requested_parts",
    "cmpWriteAllowed": False,
    "delivery": "chat_only",
}

CATALOG_LOOKUP_GATE = {"requiredBeforeJson": True, "reason": "named_service_catalog_dynamic_fields", "firstTool": "smartcmp_form_designer_list_services", "detailTool": "smartcmp_form_designer_get_catalog_detail", "resolverTool": "smartcmp_form_designer_resolve_catalog_fields", "afterKeysResolvedTool": "smartcmp_generate_catalog_context_form", "composedFieldShape": "single_requested_backend_field_only", "composedSubmitFieldVisibility": "hidden_by_default_runtime_offscreen", "sourceFieldPolicy": "resolved catalog labels are source keys only; do not create visible source fields unless the user explicitly asks for manually entered fields", "evidenceRequired": "Request Parameter Instructions or catalogPayloadFields exact field keys", "nextStep": "Resolve catalog id, read Request Parameter Instructions/catalogPayloadFields, resolve requested labels to label=key pairs, then generate only the hidden submitted composed backend field with a JSON-string value; visible fields are only user-entered custom fields."}

NEXT_STEP = (
    "Schema Form JSON schema-only user-requested fields. User-filled manual fields do not need catalog lookup. "
    "default hook is config.changeEvent; mock expression watcher; never guess catalog keys from local field names; "
    "retain last non-empty context values; no empty writes; model guard;dispatch throttle. "
    "composed values use JSON.stringify object strings and default hidden-submitted. "
    "only user-entered custom fields stay visible; source fields only when explicit; preserve business group label. "
    "customFunction also assigns model[backendKey]; resolve service-catalog fields from catalog detail first; "
    "empty common context templates. Validate the final JSON with JSON.parse, compile JS run "
    "smartcmp_validate_request_form_json. Return the complete generated JSON text directly in the chat in one fenced json code block; "
    "do not write it to a local file, workspace artifact, attachment, or download link; do not save, mount, publish, or submit"
)

CATALOG_LOOKUP_NEXT_STEP = (
    "Do not generate JSON before catalog lookup. Resolve catalog id with list/detail tools, "
    "read Request Parameter Instructions/catalogPayloadFields, run smartcmp_form_designer_resolve_catalog_fields to resolve requested labels to exact keys, then use "
    "smartcmp_generate_catalog_context_form label=key pairs; it writes a JSON object string. Fields such as department, project, owner, and name are not special-cased; resolve them from the specified service catalog when they are service-catalog fields."
)

# Match local value clauses, not whole-instruction keywords such as "create a form".
VALUE_SOURCE_PATTERNS = tuple(re.compile(pattern, re.I) for pattern in (
    r"\b(?:field\s+)?[A-Za-z_][A-Za-z0-9_\-]{0,80}\s+(?:is\s+)?(?:built|composed|made)\s+from\s*(?P<phrase>.+)$",
    r"(?:value|field)\s*(?:comes\s+from|is\s+built\s+from|is\s+composed\s+from|uses|from)\s*(?P<phrase>.+)$",
    r"^[A-Za-z_][A-Za-z0-9_\-]{0,80}\s*(?:is|=|:)\s*(?:built\s+from|composed\s+from|made\s+from|from|uses|takes)?\s*(?P<phrase>.+)$",
    r"^[A-Za-z_][A-Za-z0-9_\-]{0,80}\s*(?:takes|uses|from)\s*(?P<phrase>.+)$",
    r"(?:dynamic\s+get|get|fetch(?:es)?)\s*(?P<phrase>.+)$",
    )
)
CLAUSE_SPLIT_RE = re.compile(r"[,.;\n]+")
EXPLICIT_USER_INPUT_MARKERS = ("user input", "manual input", "user-entered", "user entered", "filled by user")

def _normalize_text(value: str) -> str: return unicodedata.normalize("NFKC", value)

def _compact(value: str) -> str: return "".join(ch for ch in _normalize_text(value).lower() if ch.isalnum())

# A catalog lookup should be driven by the value-shape the user described, not
# by a flat trigger list that treats "create a form" as dynamic.
def _template_body(text: str) -> str:
    match = re.search(r"\{([^{}]+)\}", _normalize_text(text)); return match.group(1).strip() if match else ""

def _looks_like_composed_template(text: str) -> bool:
    body = _template_body(text); return bool(body) and sum(":" in part for part in re.split(r"[,;]", body)) >= 2

def _has_catalog_like_target_name(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(re.search(r"\bform\s+for\s+[a-z0-9][a-z0-9_\-\s]{0,60}\b", normalized, re.I) or re.search(r"\b(?:for|to)\s+[a-z0-9][a-z0-9_\-\s]{0,60}\b.{0,50}\bform\b", normalized, re.I) or re.search(r"\b(?:build|create|generate)\s+(?:a\s+|an\s+)?(?!form\b)[a-z0-9][a-z0-9_\-\s]{0,60}\s+form\b", normalized, re.I))

def _has_named_catalog_target(text: str) -> bool:
    return bool(any(marker in text for marker in CATALOG_REFERENCE_MARKERS) or _has_catalog_like_target_name(text) or re.search(r"\b(?:for|to)\s+[a-z0-9][a-z0-9_\-\s]{0,60}\s+(?:create|generate|build)\b.{0,40}\bform\b", text))

# Remove formatting and composition tail words so downstream checks see only
# the candidate source fields instead of surrounding value wording.
def _strip_dynamic_phrase_noise(phrase: str) -> str:
    phrase = _normalize_text(phrase).strip()
    phrase = re.sub(r"(?:as\s+(?:a\s+)?value|as\s+content)$", "", phrase, flags=re.I).strip()
    phrase = re.sub(r"(?:(?:compose|combined?|built|generated?|create|created|formed)\s*)+$", "", phrase, flags=re.I).strip()
    return phrase


# Extract the phrase that names source fields for a derived backend value.
# Returning an empty string means the request is a normal user-entered form.
def _extract_dynamic_field_phrase(text: str) -> str:
    if body := _template_body(text):
        return body
    normalized = _normalize_text(text)
    for clause in (item.strip() for item in CLAUSE_SPLIT_RE.split(normalized) if item.strip()):
        for pattern in VALUE_SOURCE_PATTERNS:
            if match := pattern.search(clause):
                if phrase := _strip_dynamic_phrase_noise(match.group("phrase")): return phrase
    return ""


def _requires_catalog_lookup_before_json(instruction: str) -> bool:
    text = _normalize_text(instruction.strip()).lower()
    has_catalog_reference = _has_named_catalog_target(text)
    if not has_catalog_reference: return False

    # Named catalog + derived value source fields must resolve exact backend keys
    # before JSON generation. User-entered fields stay local.
    dynamic_phrase = _extract_dynamic_field_phrase(text)
    if not dynamic_phrase:
        return False
    compact_phrase = _compact(dynamic_phrase)
    if any(_compact(marker) in compact_phrase for marker in EXPLICIT_USER_INPUT_MARKERS):
        return False
    return True


def _build_meta(instruction: str) -> dict:
    catalog_lookup_required = _requires_catalog_lookup_before_json(instruction)
    meta = {
        "decision": "schema_form_definition_ready",
        "mode": "new",
        "instruction": instruction,
        "sourceRequired": False,
        "downloadAllowed": False,
        "artifactAllowed": False,
        "outputDeliveryContract": OUTPUT_DELIVERY_CONTRACT,
        "retention": "schema_form_json",
        "interactionSurface": "smartcmp_platform_service_model_form",
        "cmpWriteAllowed": False,
        "cmpWriteRequiresSecondConfirmation": False,
        "finalAction": "return_schema_form_json_only",
        "backendParameterContract": BACKEND_PARAMETER_CONTRACT,
        "backendParameterKeys": [],
        "backendParameterPayloadPreview": {},
        "designerOutputContract": DESIGNER_OUTPUT_CONTRACT,
        "catalogPolicy": CATALOG_POLICY,
        "dynamicFieldPolicy": DYNAMIC_FIELD_POLICY,
        "jsonValidationPolicy": JSON_VALIDATION_POLICY,
        "formLifecyclePolicy": FORM_LIFECYCLE_POLICY,
        "manualReference": MANUAL_REFERENCE,
        "designerPasteShape": "schema_only",
        "previewCompatible": True,
        "nextStep": NEXT_STEP,
    }
    if catalog_lookup_required:
        meta["decision"] = "catalog_lookup_required_before_form_json"
        meta["finalAction"] = "call_catalog_lookup_before_json"
        meta["catalogLookupGate"] = CATALOG_LOOKUP_GATE
        meta["nextStep"] = CATALOG_LOOKUP_NEXT_STEP
    return meta


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    instruction = (argv[0] if argv else "").strip()
    if not instruction:
        print("[ERROR] Missing required instruction argument.")
        return 1

    meta = _build_meta(instruction)
    print("[SUCCESS] Schema form preparation ready")
    print("Mode: new")
    print("CMP Saved: false")
    print("Source URL required: false")
    print("Interaction surface: SmartCMP platform service-model form")
    print("Final action: return_schema_form_json_only")
    print("##REQUEST_FORM_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
    print("##REQUEST_FORM_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
