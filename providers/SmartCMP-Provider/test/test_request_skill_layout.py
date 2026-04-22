from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
REQUEST_SKILL = PROVIDER_ROOT / "skills" / "request" / "SKILL.md"


def test_request_skill_requires_datasource_business_group_resolution():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "smartcmp_list_all_business_groups" in skill_text
    assert "datasource business-group" in skill_text
    assert "If datasource returns exactly one business group, use it silently" in skill_text
    assert "If datasource returns multiple business groups" in skill_text
    assert "uniquely normalizes to one available business group" in skill_text
    assert "If multiple business groups remain after normalization" in skill_text
    assert "do not repeat lookup scaffolding such as" in skill_text
    assert "`Found N business group(s)`" in skill_text


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

    assert 'workflow_role: "request_parent"' in skill_text
    assert "tool_submit_success_contract:" in skill_text
    assert '- "requestId"' in skill_text
    assert '- "workflowId"' in skill_text
    assert '- "Request ID"' in skill_text
