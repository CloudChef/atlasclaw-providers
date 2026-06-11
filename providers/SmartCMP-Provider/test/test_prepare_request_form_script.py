# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
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
    assert spec is not None and spec.loader is not None
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


def test_prepare_request_form_returns_schema_form_contract_without_fixed_fields() -> None:
    exit_code, stdout, stderr = run_script(
        ["Create an extension attribute form for department, project, owner, and name"]
    )

    meta = extract_meta(stderr)
    policy = meta["catalogPolicy"]

    assert exit_code == 0
    assert "[SUCCESS] Schema form preparation ready" in stdout
    assert meta["decision"] == "schema_form_definition_ready"
    assert meta["designerPasteShape"] == "schema_only"
    assert meta["previewCompatible"] is True
    assert meta["outputDeliveryContract"]["delivery"] == "chat_json_text_only"
    assert meta["outputDeliveryContract"]["localFileOutputAllowed"] is False
    assert meta["outputDeliveryContract"]["workspaceWriteAllowedForGeneratedJson"] is False
    assert meta["outputDeliveryContract"]["mustInlineCompleteJsonTextInChat"] is True
    assert "local_file_path" in meta["outputDeliveryContract"]["forbiddenDeliveryMethods"]
    assert policy["fixedRequestContextFields"] == []
    assert policy["fixedNoCatalogLookup"] == []
    assert policy["commonFieldsRequireCatalogLookup"] is True
    assert policy["catalogLookupRequiredFor"] == "all_service_catalog_dynamic_fields"
    assert "fixedRequestFieldKeys" not in policy
    assert "commonResourceRequestFields" not in policy


def test_prepare_request_form_json_like_template_requires_catalog_lookup() -> None:
    instruction = (
        "Create a form for EIP named test-eip. The form has only one backend field named mixture. "
        "mixture is {billing type: billing type value, bandwidth: bandwidth value}."
    )

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert meta["finalAction"] == "call_catalog_lookup_before_json"
    assert meta["catalogLookupGate"]["requiredBeforeJson"] is True
    assert meta["catalogLookupGate"]["resolverTool"] == "smartcmp_form_designer_resolve_catalog_fields"
    assert meta["catalogLookupGate"]["afterKeysResolvedTool"] == "smartcmp_generate_catalog_context_form"


def test_prepare_request_form_arbitrary_catalog_template_requires_catalog_lookup() -> None:
    instruction = (
        "Build CustomService form. "
        "mixture is {field a: field a value, field b: field b value}."
    )

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert meta["catalogLookupGate"]["requiredBeforeJson"] is True


def test_prepare_request_form_natural_language_composition_requires_catalog_lookup() -> None:
    instruction = (
        "Generate a form for CustomService. "
        "The form has one field mixture composed from field a and field b."
    )

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert meta["catalogLookupGate"]["requiredBeforeJson"] is True


def test_prepare_request_form_requires_catalog_lookup_for_name_and_owner_when_catalog_fields() -> None:
    instruction = "Create a service catalog form. backend_test is built from name and owner."

    exit_code, _, stderr = run_script([instruction])

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert meta["decision"] == "catalog_lookup_required_before_form_json"
    assert meta["catalogLookupGate"]["requiredBeforeJson"] is True
    assert "not special-cased" in meta["nextStep"]


def test_prepare_request_form_does_not_catalog_gate_manual_user_fields() -> None:
    instructions = [
        "Create a form for EIP with only one user-entered priority field.",
        "Create a form with user input owner and cost center.",
    ]

    for instruction in instructions:
        exit_code, _, stderr = run_script([instruction])
        meta = extract_meta(stderr)
        assert exit_code == 0
        assert meta["decision"] == "schema_form_definition_ready"
        assert "catalogLookupGate" not in meta


def test_prepare_request_form_rejects_empty_instruction() -> None:
    exit_code, stdout, stderr = run_script(["  "])

    assert exit_code == 1
    assert "[ERROR] Missing required instruction argument." in stdout
    assert "REQUEST_FORM_META" not in stderr
