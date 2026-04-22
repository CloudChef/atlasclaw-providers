from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
REQUEST_SKILL = PROVIDER_ROOT / "skills" / "request" / "SKILL.md"


def test_request_skill_requires_api_driven_business_group_resolution():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "smartcmp_list_available_bgs" in skill_text
    assert "Business Group Selection (API-driven)" in skill_text
    assert "If only one BG available" in skill_text
    assert "If multiple BGs" in skill_text


def test_request_skill_does_not_trust_runtime_form_defaults_from_catalog_metadata():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "runtimeDefaultOnly" in skill_text
    assert "**NOT** serialize that value into the request body" in skill_text
    assert "let CMP runtime form apply the real default" in skill_text


def test_request_skill_declares_provider_driven_workflow_metadata():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert 'workflow_role: "request_parent"' in skill_text
    assert "tool_submit_success_contract:" in skill_text
    assert '- "requestId"' in skill_text
    assert '- "workflowId"' in skill_text
    assert '- "Request ID"' in skill_text
