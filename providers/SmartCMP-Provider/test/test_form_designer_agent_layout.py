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
REQUEST_CONTEXT_GENERATOR_SCRIPT = SKILL_ROOT / "scripts" / "generate_request_context_form.py"
CATALOG_CONTEXT_GENERATOR_SCRIPT = SKILL_ROOT / "scripts" / "generate_catalog_context_form.py"
CATALOG_FIELD_RESOLVER_SCRIPT = SKILL_ROOT / "scripts" / "resolve_catalog_fields.py"
VALIDATE_SCRIPT = SKILL_ROOT / "scripts" / "validate_request_form_json.py"
README_FILE = PROVIDER_ROOT / "README.md"
PROVIDER_FILE = PROVIDER_ROOT / "PROVIDER.md"
SOURCE_FILES_THAT_MUST_STAY_ASCII = [
    SKILL_FILE,
    GUIDELINES_FILE,
    SHAPES_FILE,
    FETCH_SCRIPT,
    PREPARE_SCRIPT,
    CATALOG_CONTEXT_GENERATOR_SCRIPT,
    CATALOG_FIELD_RESOLVER_SCRIPT,
    VALIDATE_SCRIPT,
    Path(__file__),
    PROVIDER_ROOT / "test" / "test_generate_catalog_context_form_script.py",
    PROVIDER_ROOT / "test" / "test_prepare_request_form_script.py",
    PROVIDER_ROOT / "test" / "test_resolve_catalog_fields_script.py",
    PROVIDER_ROOT / "test" / "test_validate_request_form_json_script.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def test_form_designer_agent_layout_exists_without_fixed_context_generator() -> None:
    assert SKILL_ROOT.is_dir()
    assert SKILL_FILE.is_file()
    assert GUIDELINES_FILE.is_file()
    assert SHAPES_FILE.is_file()
    assert FETCH_SCRIPT.is_file()
    assert PREPARE_SCRIPT.is_file()
    assert not REQUEST_CONTEXT_GENERATOR_SCRIPT.exists()
    assert CATALOG_CONTEXT_GENERATOR_SCRIPT.is_file()
    assert CATALOG_FIELD_RESOLVER_SCRIPT.is_file()
    assert VALIDATE_SCRIPT.is_file()


def test_form_designer_agent_declares_catalog_tools_not_request_context_tool() -> None:
    skill_text = _read(SKILL_FILE)
    lowered = skill_text.lower()

    assert "name: form-designer-agent" in skill_text
    assert 'provider_type: "smartcmp"' in skill_text
    assert 'tool_prepare_name: "smartcmp_prepare_request_form"' in skill_text
    assert 'tool_catalog_context_name: "smartcmp_generate_catalog_context_form"' in skill_text
    assert 'tool_catalog_field_resolver_name: "smartcmp_form_designer_resolve_catalog_fields"' in skill_text
    assert 'tool_fetch_name: "smartcmp_fetch_request_form_source"' in skill_text
    assert 'tool_validate_name: "smartcmp_validate_request_form_json"' in skill_text
    assert 'tool_catalogs_name: "smartcmp_form_designer_list_services"' in skill_text
    assert 'tool_catalog_detail_name: "smartcmp_form_designer_get_catalog_detail"' in skill_text
    assert "generate form" in lowered
    assert "smartcmp_generate_request_context_form" not in skill_text
    assert "generate_request_context_form.py" not in skill_text
    assert "smartcmp_submit_request" not in skill_text


def test_form_designer_agent_docs_are_compact_and_single_page_based() -> None:
    skill_text = _read(SKILL_FILE)
    guidelines = _read(GUIDELINES_FILE)
    shapes = _read(SHAPES_FILE)
    prepare = _read(PREPARE_SCRIPT)

    assert skill_text.isascii()
    assert guidelines.isascii()
    assert shapes.isascii()
    assert len(skill_text.splitlines()) <= 240
    assert len(guidelines.splitlines()) <= 240
    assert len(shapes.splitlines()) <= 120
    assert len(prepare.splitlines()) <= 300
    assert "pageId=123109820" in guidelines
    assert "single Confluence page" in guidelines
    assert "do not crawl child pages" in guidelines


def test_form_designer_agent_sources_stay_ascii_without_unicode_escapes() -> None:
    unicode_escape_prefix = "\\" + "u"
    for path in SOURCE_FILES_THAT_MUST_STAY_ASCII:
        text = _read(path)
        assert text.isascii(), f"{path} contains non-ASCII source text"
        assert unicode_escape_prefix not in text, f"{path} contains Unicode escape source text"


def test_prepare_catalog_gate_has_no_product_name_shortcuts() -> None:
    prepare = _read(PREPARE_SCRIPT)

    assert "eip|rds|vm|ecs|ip|linux|windows" not in prepare.lower()


def test_form_designer_agent_documents_catalog_required_for_service_catalog_fields() -> None:
    combined = _normalized("\n".join([_read(SKILL_FILE), _read(GUIDELINES_FILE), _read(PREPARE_SCRIPT)]))

    assert "do not special-case department, project, owner, or name" in combined
    assert "user must specify the target service catalog before any service-catalog field is read" in combined
    assert "resolve them from the specified service catalog" in combined
    assert "smartcmp_form_designer_resolve_catalog_fields" in combined
    assert "smartcmp_generate_catalog_context_form" in combined
    assert "label=key pairs" in combined
    assert "request parameter instructions" in combined
    assert "catalogpayloadfields" in combined
    assert "@request:department" not in combined
    assert "fixed request-context fields" not in combined
    assert "fixed request fields" not in combined
    assert "do not ask for a service catalog name or url" not in combined


def test_form_designer_agent_keeps_json_output_boundary() -> None:
    combined = _normalized("\n".join([_read(SKILL_FILE), _read(GUIDELINES_FILE)]))

    assert "return the generated json as chat text in one fenced `json` code block" in combined
    assert "complete json text in the chat interface" in combined
    assert "never create a local `.json` file" in combined
    assert "do not return a path" in combined
    assert "never return a local path" in combined
    assert "do not create, write, attach, or mention a `.json` file" in combined
    assert "do not use workspace artifacts or download links" in combined
    assert "do not save, mount, publish, or submit anything in cmp" in combined


def test_fetch_source_uses_same_chat_only_output_contract() -> None:
    fetch_text = _read(FETCH_SCRIPT)

    assert '"localFileOutputAllowed": False' in fetch_text
    assert '"workspaceWriteAllowedForGeneratedJson": False' in fetch_text
    assert '"mustInlineCompleteJsonTextInChat": True' in fetch_text
    assert '"local_file_path"' in fetch_text


def test_provider_docs_describe_form_designer_as_json_rendering_agent() -> None:
    combined = "\n".join([_read(README_FILE), _read(PROVIDER_FILE)])
    lowered = combined.lower()

    assert "Form Designer Agent" in combined
    assert "schema form json" in lowered
    assert "backend parameters" in lowered
    assert "service catalog" in lowered
    assert "service-model form" in lowered
    assert "smartcmp_submit_request" not in combined
