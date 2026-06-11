# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Recognize a SmartCMP service-model form URL as Schema Form source context.

Usage:
  python fetch_request_form_source.py <same_host_service_model_form_url>

Output:
  - Human-readable Schema Form source summary
  - ##REQUEST_FORM_SOURCE_META_START## ... ##REQUEST_FORM_SOURCE_META_END##
      JSON object with source context for agent processing
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import requests

try:
    from _common import require_config
except ImportError:
    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import require_config


BASE_URL, _, HEADERS, _ = require_config()

UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

BACKEND_PARAMETER_CONTRACT = {
    "shape": "kv_json_object",
    "sourcePolicy": "shape_dependent",
    "source": "shape_dependent",
    "sourcesByShape": {
        "smartcmp_content": "content.model",
        "schema_only": "properties",
        "angular2_schema": "properties",
        "angular1_schema_form_model": "schema.properties and form[].key",
        "formio_components": "components[].key",
    },
    "runtimeValue": "final_rendered_form_values",
    "catalogRequestLocation": "params_when_service_catalog_model_form",
    "genericRequestLocation": "genericRequest.processForm_when_process_form",
}

DESIGNER_OUTPUT_CONTRACT = {
    "primaryJson": "chat_fenced_json_value",
    "sourceContextKey": "designerPasteJson",
    "shapePolicy": "preserve_target_module_shape",
    "supportedSourceShapes": [
        "smartcmp_content",
        "schema_only",
        "formio_components",
        "angular1_schema_form_model",
        "angular2_schema",
    ],
    "formEntityJsonIsOptional": True,
    "forceModelSchemaOptions": False,
    "expertModePreviewDefault": "schema_only",
    "previewPasteTargets": {
        "visual_designer_expert_mode": "schema_only",
        "schema_renderer": "schema_only",
        "smartcmp_content_editor": "smartcmp_content",
        "angular1_schema_form_editor": "angular1_schema_form_model",
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


def _base_origin() -> str:
    parsed = urlsplit(BASE_URL)
    path = parsed.path.rstrip("/")
    if path.endswith("/platform-api"):
        path = path[: -len("/platform-api")]
    return urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))


def _normalized_host(url: str) -> str:
    parsed = urlsplit(url)
    return (parsed.hostname or "").lower()


def _sanitize_internal_ids(value: str) -> str:
    return UUID_PATTERN.sub("[uuid]", value or "")


def _route_parts(source: str) -> tuple[str, str]:
    parsed = urlsplit(source)
    route = parsed.fragment or parsed.path
    route_path, _, route_query = route.partition("?")
    return route_path.strip("/"), route_query


def _extract_edit_form_id(source: str) -> str:
    route_path, _ = _route_parts(source)
    for prefix in (
        "main/service-model/forms/edit/",
        "main/service-model/forms/design/",
    ):
        if route_path.startswith(prefix):
            return unquote(route_path[len(prefix) :].strip("/"))
    return ""


def _is_service_model_form_url(source: str) -> bool:
    route_path, _ = _route_parts(source)
    return route_path == "main/service-model/forms" or bool(_extract_edit_form_id(source))


def _validate_source(value: str) -> str:
    source = value.strip()
    if not source:
        raise ValueError("Missing required source_request_url argument.")

    parsed = urlsplit(source)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("source_request_url must be a same-host SmartCMP service-model form URL.")
    if _normalized_host(source) != _normalized_host(_base_origin()):
        raise ValueError("source_request_url is outside configured SmartCMP host.")
    if not _is_service_model_form_url(source):
        raise ValueError("source_request_url must be a same-host SmartCMP service-model form URL.")
    return source


def _fetch_form_definition(form_id: str) -> dict[str, Any]:
    try:
        response = requests.get(
            f"{BASE_URL}/forms/{form_id}",
            headers=HEADERS,
            verify=False,
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(type(exc).__name__) from exc

    if response.status_code != 200:
        message = _sanitize_internal_ids(getattr(response, "text", "") or "SmartCMP returned an error.")
        raise RuntimeError(f"HTTP {response.status_code}: {message}")

    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Invalid JSON response.") from exc

    return payload if isinstance(payload, dict) else {"raw": payload}


def _extract_form_content(form_definition: dict[str, Any]) -> dict[str, Any]:
    content = form_definition.get("content")
    if isinstance(content, dict):
        return content

    extracted: dict[str, Any] = {}
    for key in ("model", "schema", "options", "components"):
        value = form_definition.get(key)
        if value is not None:
            extracted[key] = value
    return extracted


def _append_unique(target: list[str], value: object) -> None:
    key = str(value or "").strip()
    if key and key not in target:
        target.append(key)


def _component_default(component: dict[str, Any]) -> Any:
    if "defaultValue" in component:
        return component.get("defaultValue")
    if "default" in component:
        return component.get("default")
    return None


def _schema_property_default(property_schema: dict[str, Any]) -> Any:
    if "defaultValue" in property_schema:
        return property_schema.get("defaultValue")
    if "default" in property_schema:
        return property_schema.get("default")
    return None


def _backend_parameter_contract(designer_paste_shape: str) -> dict[str, Any]:
    contract = dict(BACKEND_PARAMETER_CONTRACT)
    sources_by_shape = dict(BACKEND_PARAMETER_CONTRACT["sourcesByShape"])
    contract["sourcesByShape"] = sources_by_shape
    contract["source"] = sources_by_shape.get(designer_paste_shape, "shape_dependent")
    return contract


def _preview_warnings(designer_paste_shape: str) -> tuple[bool, list[str]]:
    if designer_paste_shape in {"schema_only", "angular2_schema"}:
        return True, []
    if designer_paste_shape == "formio_components":
        return False, ["Form.io components may not preview in SmartCMP schema expert mode; use schema-only JSON for that paste target."]
    if designer_paste_shape == "smartcmp_content":
        return False, ["SmartCMP content JSON may not preview in visual designer expert mode unless that editor accepts content wrappers."]
    if designer_paste_shape == "angular1_schema_form_model":
        return False, ["Angular1 schema/form/model JSON may not preview in visual designer expert mode unless that editor accepts Angular1 schema form."]
    return False, ["Unknown form shape may not preview in visual designer expert mode."]


def _build_designer_paste_json(form_definition: dict[str, Any], content: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    has_inner_content = isinstance(form_definition.get("content"), dict)
    if has_inner_content and isinstance(content.get("schema"), dict):
        return "schema_only", content["schema"]

    if has_inner_content and isinstance(content.get("components"), list):
        return "formio_components", {"components": content["components"]}

    if isinstance(form_definition.get("components"), list):
        return "formio_components", {"components": form_definition["components"]}

    if isinstance(form_definition.get("schema"), dict) and isinstance(form_definition.get("form"), list):
        paste = {"schema": form_definition["schema"], "form": form_definition["form"]}
        if isinstance(form_definition.get("model"), dict):
            paste["model"] = form_definition["model"]
        if isinstance(form_definition.get("i18n"), dict):
            paste["i18n"] = form_definition["i18n"]
        return "angular1_schema_form_model", paste

    if isinstance(form_definition.get("schema"), dict):
        return "schema_only", form_definition["schema"]

    if isinstance(content, dict) and content:
        return "unknown_content", content

    return "empty", {}


def _extract_backend_parameter_payload(form_definition: dict[str, Any]) -> tuple[list[str], dict[str, Any], dict[str, Any], str, dict[str, Any]]:
    content = _extract_form_content(form_definition)
    model = content.get("model")
    if not isinstance(model, dict):
        model = {}

    schema = content.get("schema")
    if not isinstance(schema, dict):
        schema = {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}

    components = content.get("components")
    if not isinstance(components, list):
        components = form_definition.get("components")
    if not isinstance(components, list):
        components = []

    keys: list[str] = []
    for key in model:
        _append_unique(keys, key)
    for key in properties:
        _append_unique(keys, key)
    for component in components:
        if isinstance(component, dict):
            _append_unique(keys, component.get("key"))

    component_by_key = {
        str(component.get("key")): component
        for component in components
        if isinstance(component, dict) and component.get("key")
    }
    payload: dict[str, Any] = {}
    for key in keys:
        if key in model:
            payload[key] = model[key]
        elif isinstance(properties.get(key), dict):
            payload[key] = _schema_property_default(properties[key])
        elif isinstance(component_by_key.get(key), dict):
            payload[key] = _component_default(component_by_key[key])
        else:
            payload[key] = None

    designer_paste_shape, designer_paste_json = _build_designer_paste_json(form_definition, content)

    return keys, payload, content, designer_paste_shape, designer_paste_json


def _build_meta(source: str) -> dict[str, Any]:
    route_path, route_query = _route_parts(source)
    form_id = _extract_edit_form_id(source)
    mode = "update" if form_id else "create"
    source_type = "smartcmp_service_model_form_edit" if form_id else "smartcmp_service_model_form_list"
    form_definition = _fetch_form_definition(form_id) if form_id else {}
    (
        backend_parameter_keys,
        backend_parameter_payload,
        extracted_content,
        designer_paste_shape,
        designer_paste_json,
    ) = _extract_backend_parameter_payload(form_definition)
    preview_compatible, warnings = _preview_warnings(designer_paste_shape)
    return {
        "decision": "schema_form_source_ready",
        "mode": mode,
        "sourceType": source_type,
        "sourceUrl": _sanitize_internal_ids(source),
        "routePath": route_path,
        "routeQuery": route_query,
        "formId": form_id,
        "formDefinition": form_definition,
        "requestParams": {},
        "backendParameterContract": _backend_parameter_contract(designer_paste_shape),
        "backendParameterKeys": backend_parameter_keys,
        "backendParameterPayloadPreview": backend_parameter_payload,
        "designerOutputContract": DESIGNER_OUTPUT_CONTRACT,
        "designerPasteShape": designer_paste_shape,
        "designerPasteJson": designer_paste_json,
        "previewCompatible": preview_compatible,
        "extractedFormContent": extracted_content,
        "downloadAllowed": False,
        "artifactAllowed": False,
        "outputDeliveryContract": OUTPUT_DELIVERY_CONTRACT,
        "retention": "schema_form_json",
        "interactionSurface": "smartcmp_platform_service_model_form",
        "cmpWriteAllowed": False,
        "cmpWriteRequiresSecondConfirmation": False,
        "finalAction": "return_schema_form_json_only",
        "nextStep": (
            "Use the service-model form URL as Schema Form source context. "
            "Generate or update SmartCMP Schema Form JSON around backend "
            "parameters collected at request time. Return the generated or "
            "updated JSON as chat text in one fenced json code block. Do not "
            "create, write, attach, or mention a JSON file, and do not use "
            "workspace artifacts or download links. Do not save, mount, "
            "publish, or submit anything in CMP."
        ),
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        source = _validate_source(argv[0] if argv else "")
    except ValueError as error:
        print(f"[ERROR] {error}")
        return 1

    try:
        meta = _build_meta(source)
    except RuntimeError as error:
        print(f"[ERROR] {error}")
        return 1

    print("[SUCCESS] Schema form source fetched" if meta.get("formId") else "[SUCCESS] Schema form source recognized")
    print(f"Source type: {meta['sourceType']}")
    if meta.get("formId"):
        print(f"Form ID: {_sanitize_internal_ids(meta['formId'])}")
    print("CMP Saved: false")
    print("Interaction surface: SmartCMP platform service-model form")
    print("##REQUEST_FORM_SOURCE_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
    print("##REQUEST_FORM_SOURCE_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
