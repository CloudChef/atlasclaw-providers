# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROVIDER_ROOT / "skills" / "form-designer-agent"
SKILL_FILE = SKILL_ROOT / "SKILL.md"
GUIDELINES_FILE = SKILL_ROOT / "references" / "form-guidelines.md"
SHAPES_FILE = SKILL_ROOT / "references" / "form-module-shapes.md"
FETCH_SCRIPT = SKILL_ROOT / "scripts" / "fetch_request_form_source.py"
PREPARE_SCRIPT = SKILL_ROOT / "scripts" / "prepare_request_form.py"
CONTEXT_GENERATOR_SCRIPT = SKILL_ROOT / "scripts" / "generate_request_context_form.py"
CATALOG_CONTEXT_GENERATOR_SCRIPT = SKILL_ROOT / "scripts" / "generate_catalog_context_form.py"
CATALOG_FIELD_RESOLVER_SCRIPT = SKILL_ROOT / "scripts" / "resolve_catalog_fields.py"
VALIDATE_SCRIPT = SKILL_ROOT / "scripts" / "validate_request_form_json.py"
SAVE_SCRIPT = SKILL_ROOT / "scripts" / "save_service_model_form.py"
PERSIST_SCRIPT = SKILL_ROOT / "scripts" / "persist_form_draft.py"
OLD_FETCH_SCRIPT = SKILL_ROOT / "scripts" / "fetch_form_source.py"
OLD_PREPARE_SCRIPT = SKILL_ROOT / "scripts" / "prepare_form_draft.py"
REQUEST_GUIDELINES_FILE = SKILL_ROOT / "references" / "request-form-guidelines.md"
README_FILE = PROVIDER_ROOT / "README.md"
PROVIDER_FILE = PROVIDER_ROOT / "PROVIDER.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def test_form_designer_agent_layout_exists() -> None:
    assert SKILL_ROOT.is_dir()
    assert SKILL_FILE.is_file()
    assert GUIDELINES_FILE.is_file()
    assert SHAPES_FILE.is_file()
    assert FETCH_SCRIPT.is_file()
    assert PREPARE_SCRIPT.is_file()
    assert CONTEXT_GENERATOR_SCRIPT.is_file()
    assert CATALOG_CONTEXT_GENERATOR_SCRIPT.is_file()
    assert CATALOG_FIELD_RESOLVER_SCRIPT.is_file()
    assert VALIDATE_SCRIPT.is_file()
    assert not SAVE_SCRIPT.exists()
    assert not PERSIST_SCRIPT.exists()
    assert not OLD_FETCH_SCRIPT.exists()
    assert not OLD_PREPARE_SCRIPT.exists()
    assert not REQUEST_GUIDELINES_FILE.exists()


def test_form_designer_agent_declares_provider_metadata_and_tools() -> None:
    skill_text = _read(SKILL_FILE)
    lowered = skill_text.lower()

    assert "name: form-designer-agent" in skill_text
    assert 'provider_type: "smartcmp"' in skill_text
    assert 'instance_required: "true"' in skill_text
    assert "agent-form-designer" in skill_text
    assert "backend parameters" in skill_text
    assert 'tool_prepare_name: "smartcmp_prepare_request_form"' in skill_text
    assert 'tool_prepare_entrypoint: "scripts/prepare_request_form.py"' in skill_text
    assert '"required": ["instruction"]' in skill_text
    assert 'tool_context_name: "smartcmp_generate_request_context_form"' in skill_text
    assert 'tool_context_entrypoint: "scripts/generate_request_context_form.py"' in skill_text
    assert '"required":["backend_key","title","fields"]' in skill_text
    assert "include_source_fields" in skill_text
    assert 'tool_catalog_context_name: "smartcmp_generate_catalog_context_form"' in skill_text
    assert 'tool_catalog_context_entrypoint: "scripts/generate_catalog_context_form.py"' in skill_text
    assert "label=key pairs from scanned catalog instructions" in skill_text
    assert 'tool_catalog_field_resolver_name: "smartcmp_form_designer_resolve_catalog_fields"' in skill_text
    assert 'tool_catalog_field_resolver_entrypoint: "scripts/resolve_catalog_fields.py"' in skill_text
    assert 'tool_fetch_name: "smartcmp_fetch_request_form_source"' in skill_text
    assert 'tool_fetch_entrypoint: "scripts/fetch_request_form_source.py"' in skill_text
    assert '"required": ["source_request_url"]' in skill_text
    assert 'tool_validate_name: "smartcmp_validate_request_form_json"' in skill_text
    assert 'tool_validate_entrypoint: "scripts/validate_request_form_json.py"' in skill_text
    assert '"required": ["form_json"]' in skill_text
    assert 'tool_catalogs_name: "smartcmp_form_designer_list_services"' in skill_text
    assert 'tool_catalog_detail_name: "smartcmp_form_designer_get_catalog_detail"' in skill_text
    assert "same-host SmartCMP service-model form URL" in skill_text
    assert "generate form" in lowered
    assert "form generation" in lowered
    assert "request form generation" in lowered
    assert "tool_save_" not in skill_text
    assert "smartcmp_save_service_model_form" not in skill_text
    assert "save_service_model_form.py" not in skill_text
    assert "smartcmp_submit_request" not in skill_text
    assert "tool_persist" not in skill_text
    assert "submit to cmp" not in lowered


def test_form_designer_agent_docs_are_compact_and_single_page_based() -> None:
    skill_text = _read(SKILL_FILE)
    guidelines = _read(GUIDELINES_FILE)
    shapes = _read(SHAPES_FILE)
    prepare = _read(PREPARE_SCRIPT)

    assert skill_text.isascii()
    assert guidelines.isascii()
    assert shapes.isascii()
    assert len(skill_text.splitlines()) <= 260
    assert len(guidelines.splitlines()) <= 260
    assert len(shapes.splitlines()) <= 120
    assert len(prepare.splitlines()) <= 320
    assert "pageId=123109820" in guidelines
    assert "single Confluence page" in guidelines
    assert "do not crawl child pages" in guidelines
    assert "20545965" not in guidelines


def test_form_designer_agent_validator_stays_compact_and_commented() -> None:
    validator = _read(VALIDATE_SCRIPT)
    lines = validator.splitlines()

    assert len(lines) <= 760
    for index, line in enumerate(lines):
        if line.startswith("def "):
            assert lines[index + 1].strip().startswith("# "), line


def test_form_designer_agent_has_no_catalog_specific_field_hardcoded_lists() -> None:
    prepare = _read(PREPARE_SCRIPT)
    resolver = _read(CATALOG_FIELD_RESOLVER_SCRIPT)
    validator = _read(VALIDATE_SCRIPT)
    docs = "\n".join([_read(SKILL_FILE), _read(GUIDELINES_FILE)])

    assert "CATALOG_SPECIFIC_CONTEXT_MARKERS" not in prepare
    assert "SEMANTIC_LABEL_TOKENS" not in resolver
    assert "CATALOG_SOURCE_FIELD_KEYS" not in validator
    for token in (
        "InternetChargeType",
        "Bandwidth",
        "InstanceChargeType",
        "resource_group_id",
        "billing-type/bandwidth",
        "application system",
        "availability zone",
    ):
        assert token not in docs


def test_catalog_context_generator_uses_named_runtime_fragments() -> None:
    generator = _read(CATALOG_CONTEXT_GENERATOR_SCRIPT)

    for helper in (
        "_js_runtime_preamble",
        "_js_text_helpers",
        "_js_dom_helpers",
        "_js_catalog_value_helpers",
        "_js_request_context_helpers",
        "_js_model_sync_helpers",
    ):
        assert f"def {helper}(" in generator

    assert "''.join(" in generator
    assert "config.value.expression" not in generator


def test_form_designer_agent_documents_core_schema_form_contract() -> None:
    combined = _normalized(
        "\n".join([_read(SKILL_FILE), _read(GUIDELINES_FILE), _read(SHAPES_FILE)])
    )

    assert "schema form json" in combined
    assert "designerpastejson" in combined
    assert "bare json value itself" in combined
    assert "preserve the target module shape" in combined
    assert "do not force every form into model/schema/options" in combined
    assert "model" in combined
    assert "schema" in combined
    assert "properties" in combined
    assert "fieldsets" in combined
    assert "columnsets" in combined
    assert "config.value" in combined
    assert "changeevent" in combined
    assert "sourceconfigparamter" in combined
    assert "schemaformvalid" in combined
    assert "return the generated json as chat text in one fenced `json` code block" in combined
    assert "do not create, write, attach, or mention a `.json` file" in combined


def test_form_designer_agent_keeps_catalog_lookup_narrow() -> None:
    combined = _normalized("\n".join([_read(SKILL_FILE), _read(GUIDELINES_FILE)]))

    assert "common resource request fields" in combined
    assert "department, project, owner, and name" in combined
    assert "can be dynamically read from the request page" in combined
    assert "businessgroup" in combined
    assert "sourceconfigparamter.businessgroupid" in combined
    assert "sourceconfigparamter.projectid" in combined
    assert "sourceconfigparamter.ownerid" in combined
    assert "sourceconfigparamter.name" in combined
    assert "not `sourceconfigparamter.name`" in combined
    assert "vm.deploymentobj.businessgroupid" in combined
    assert "vm.selectedgroup" in combined
    assert "vm.selecteduser.id" in combined
    assert "vm.deploymentobj.name" in combined
    assert "treat these id values as ids" in combined
    assert "concatenating human-readable output values" in combined
    assert "do not generate common resource request fields as user input fields just to read request context" in combined
    assert "explicitly requests fixed context values as separate visible business properties" in combined
    assert "raw source fields and one composed field" in combined
    assert "raw synchronized source fields plus the hidden-submitted composed field" in combined
    assert "preserve the requested display meaning" in combined
    assert "business group versus department" in combined
    assert "do not use common resource request fields as refresh trigger fields" in combined
    assert "use a non-common refresh trigger field" in combined
    assert "do not read common request context from `model.name` or `model.owner`" in combined
    assert "do not call catalog tools for common resource request fields only" in combined
    assert "fixed request fields" in combined
    assert "do not ask for a service catalog name or url" in combined
    assert "inspect request parameter instructions" in combined
    assert "`smartcmp_form_designer_get_catalog_detail`/`smartcmp_form_designer_list_services`" in combined
    assert "for department, project, owner, or name" in combined
    assert "user-filled special fields do not need a service catalog name or url" in combined
    assert "catalog-specific dynamic fields" in combined
    assert "named service catalogs" in combined
    assert "any named service catalog" in combined
    assert "map requested labels to exact keys" in combined
    assert "smartcmp_form_designer_resolve_catalog_fields" in combined
    assert "resolve requested labels to label=key pairs" in combined
    assert "never guessed display labels alone" in combined
    assert "only department, project, owner, and name are fixed request-context fields" in combined
    assert "every other dynamic field must come from catalog metadata" in combined
    assert "@request:department" in combined
    assert "all non-fixed labels as catalog-specific" in combined
    assert "cataloglookupgate" in combined
    assert "stop json generation" in combined
    assert "smartcmp_generate_catalog_context_form" in combined
    assert "smartcmp_form_designer_get_catalog_detail" in combined
    assert "request parameter instructions" in combined
    assert "catalogpayloadfields" in combined
    assert "catalogfieldkeys.payloadfields" in combined
    assert "when they are missing" in combined
    assert "before asking or guessing" in combined
    assert "do not call `smartcmp_prepare_request_form` repeatedly to discover catalog fields" in combined
    assert "generated form javascript cannot call atlas agent tools" in combined


def test_form_designer_agent_documents_output_and_write_boundary() -> None:
    combined = "\n".join([_read(SKILL_FILE), _read(GUIDELINES_FILE)])
    lowered = combined.lower()
    normalized = _normalized(combined)

    assert "smartcmp_submit_request_form" not in combined
    assert "smartcmp_persist_form_draft" not in combined
    assert "persist_form_draft" not in combined
    assert "download_paths" not in combined
    assert "workspace://" not in combined
    assert "conversation draft" not in lowered
    assert "submitted=true" not in lowered
    assert "submitted=false" not in lowered
    assert "return the generated json as chat text in one fenced `json` code block" in normalized
    assert "do not create, write, attach, or mention a `.json` file" in normalized
    assert "do not use workspace artifacts or download links" in normalized
    assert "never say the file has been written to the workspace" in normalized
    assert "save, mount, publish, or submit" in normalized


def test_form_designer_agent_documents_json_validation_and_js_hook_rules() -> None:
    combined_raw = "\n".join(
        [_read(SKILL_FILE), _read(GUIDELINES_FILE), _read(PREPARE_SCRIPT)]
    )
    combined = _normalized(combined_raw)

    assert "validate the final json with `json.parse`" in combined
    assert "d4fe8a9e-7fb1-43eb-a8fc-c45b5de12d4c" not in combined_raw
    assert "dcfbd360-4910-4dc5-942d-3323a1c204fd" not in combined_raw
    assert "reference form urls" not in combined
    assert "successful existing form scripts" in combined
    assert "config.changeevent" in combined
    assert "config.value.source: mock" in combined
    assert "config.value.expression" in combined
    assert "smartcmp_generate_request_context_form" in combined
    assert "do not hand-write the javascript" in combined
    assert "never invent a new context-sync expression" in combined
    assert "preserve the user's output labels" in combined
    assert "do not replace requested labels with resolved backend keys" in combined
    assert "after resolver success, call `smartcmp_generate_catalog_context_form` immediately" in combined
    assert "do not ask whether the composed field should be visible" in combined
    assert "for `config.value.expression` mock watcher, use `function(model, sourceparams, schema, ...)`" in combined
    assert "do not use the changeevent signature there" in combined
    assert "properties.<fieldkey>.config.changeevent" in combined
    assert "schema.properties.<fieldkey>.config.changeevent" in combined
    assert "function(itemid, schema, model, sourceparams)" in combined
    assert "third argument is the submitted model" in combined
    assert "fourth argument is sourceparams" in combined
    assert "model[backendkey] = value" in combined
    assert "customfunction must also assign `model[backendkey] = value`" in combined
    assert "do not generate `model.name || ''` or `model.owner || ''`" in combined
    assert "do not generate direct-only `sourceparams.name` or `sourceparams.owner` reads" in combined
    assert "never read `sourceparams.name` for request name" in combined
    assert "never concatenate raw `ownerid` or `selecteduser.id` as owner display text" in combined
    assert "fixed request-context fields (name/owner/department/project)" in combined
    assert "do not hard-code example keys, labels, or field combinations" in combined
    assert "hidden-submitted composed field" in combined
    assert "raw source fields stay visible raw strings" in combined
    assert "do not normalize the visible label to department" in combined
    assert "never read fixed context from `window.vm`, `window.sourceconfigparamter`, or unqualified global `vm`" in combined
    assert "do not use jquery owner selectors" in combined
    assert "do not store watcher state in a local `var interval = null`" in combined
    assert "do not clear the watcher interval inside its callback after the first computed value" in combined
    assert "retain the last non-empty value for each fixed field" in combined
    assert "guard `model[backendkey]` with `object.defineproperty`" in combined
    assert "never overwrite a correct computed value with empty or unresolved context" in combined
    assert "if the current read is empty, return the previous good field/model value and do not write" in combined
    assert "throttle input/change dispatches" in combined
    assert "restore dom/model silently for the same computed value" in combined
    assert "do not return empty common context templates" in combined
    assert "name/owner or department/owner" in combined
    assert "non-empty unresolved marker" in combined
    assert "layered context resolution" in combined
    assert "sourceparams.businessgroupid" in combined
    assert "sourceparams.projectid" in combined
    assert "sourceparams.ownerid" in combined
    assert "not passed as `sourceparams.name`" in combined
    assert "one physical line" in combined
    assert "do not put dynamic logic in root-level changeevent" in combined
    assert "do not put field definitions under `options.fields`" in combined
    assert "computed_values" in combined
    assert "generated form javascript cannot call atlas agent tools" in combined


def test_form_designer_agent_documents_renderable_refresh_rules() -> None:
    combined = _normalized("\n".join([_read(SKILL_FILE), _read(GUIDELINES_FILE)]))

    assert "fenced json block must contain the bare json value itself" in combined
    assert "do not wrap schema-only output in `designerpastejson`" in combined
    assert "editable string request inputs should use `widget.id: \"string\"`" in combined
    assert "do not use `widget.id: \"text\"` for editable request input fields" in combined
    assert "changeevent runs only when its owning field changes" in combined
    assert "the owning field must allow request modification" in combined
    assert "provide a visible editable trigger field" in combined
    assert "do not use hidden fields as refresh trigger fields" in combined
    assert "hidden fields cannot be changed by the requester" in combined
    assert "when no user-entered refresh field is wanted for common request context, use a rendered backend field with a mock expression watcher" in combined
    assert "generated composed backend fields are hidden off-screen by default while still submitting" in combined
    assert "vm.deploymentobj.name" in combined
    assert "vm.selecteduser" in combined
    assert "sourceconfigparamter.ownerid" in combined
    assert "do not use a one-shot dom query" in combined
    assert "missing watcher" in combined
    assert "return the computed value instead of literal `auto_sync_pending`" in combined
    assert "use `config.value.customfunction` only when an existing source proves the renderer executes it" in combined
    assert "do not add `_trigger_*` fields solely for refresh" in combined
    assert "do not put `config.value.customfunction` on hidden computed fields" in combined
    assert "do not rely on submit to refresh computed values" in combined
    assert "clear the previous interval before starting a new one" in combined
    assert "ngmodel `$setviewvalue`" in combined
    assert "auto_sync_pending" in combined
    assert "return the computed value" in combined
    assert "dispatch `input` and `change` events" in combined


def test_form_designer_agent_documents_successful_runtime_patterns() -> None:
    combined_raw = "\n".join([_read(SKILL_FILE), _read(GUIDELINES_FILE)])
    combined = _normalized(combined_raw)

    assert "derived from successful forms" in combined
    assert "do not hardcode successful form urls or uuids" in combined
    assert "rendered backend field plus visible trigger field" in combined
    assert "rendered backend field with field-level changeevent" in combined
    assert "rendered backend field with config.value mock expression watcher" in combined
    assert "hide the rendered composed field off-screen while keeping submission alive" in combined
    assert "hidden computed target plus customfunction is forbidden" in combined
    assert "run `smartcmp_validate_request_form_json` before returning" in combined
    assert "compile every generated function string with `new function`" in combined
    assert "try block must have `catch` or `finally`" in combined
    assert "d4fe8a9e-7fb1-43eb-a8fc-c45b5de12d4c" not in combined_raw
    assert "dcfbd360-4910-4dc5-942d-3323a1c204fd" not in combined_raw


def test_form_designer_agent_supports_new_and_existing_form_modes_without_cmp_writes() -> None:
    combined = _normalized("\n".join([_read(SKILL_FILE), _read(GUIDELINES_FILE)]))

    assert "new form" in combined
    assert "existing form url" in combined
    assert "call `smartcmp_fetch_request_form_source`" in combined
    assert "output schema-only root json" in combined
    assert "not outer `model/schema`" in combined
    assert "modify only the requested parts" in combined
    assert "output to chat only" in combined
    assert "do not save, mount, publish, or submit anything in cmp" in combined


def test_provider_docs_describe_form_designer_as_json_rendering_agent() -> None:
    combined = "\n".join([_read(README_FILE), _read(PROVIDER_FILE)])
    lowered = combined.lower()

    assert "Form Designer Agent" in combined
    assert "schema form json" in lowered
    assert "backend parameters" in lowered
    assert "service catalog" in lowered
    assert "service-model form" in lowered
    assert "target form module" in lowered
    assert "designer paste json" in lowered
    assert "conversation draft" not in lowered
    assert "two-stage confirmation" not in lowered
    assert "smartcmp_save_service_model_form" not in combined
    assert "pending work-order" not in lowered
    assert "smartcmp_submit_request" not in combined


def test_provider_frontmatter_routes_form_generation_to_form_designer_agent() -> None:
    provider_text = _read(PROVIDER_FILE)
    frontmatter = provider_text.split("---", 2)[1].lower()

    assert "form designer" in frontmatter
    assert "schema form" in frontmatter
    assert "schema form json" in frontmatter
    assert "request form" in frontmatter
    assert "catalog form" in frontmatter
    assert "backend parameter form" in frontmatter
    assert "generate, create, review, rewrite, or modify" in frontmatter
    assert "use request skill" in frontmatter
