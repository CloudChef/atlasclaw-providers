from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
REQUEST_SKILL = PROVIDER_ROOT / "skills" / "request" / "SKILL.md"


def test_request_skill_requires_datasource_business_group_resolution():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "smartcmp_list_all_business_groups" in skill_text
    assert "datasource business-group" in skill_text
    assert "If datasource returns exactly one business group, use it silently" in skill_text
    assert "If datasource returns multiple business groups" in skill_text


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
