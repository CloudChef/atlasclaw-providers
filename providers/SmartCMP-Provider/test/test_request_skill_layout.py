from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
REQUEST_SKILL = PROVIDER_ROOT / "skills" / "request" / "SKILL.md"


def test_request_skill_requires_datasource_business_group_resolution():
    skill_text = REQUEST_SKILL.read_text(encoding="utf-8")

    assert "smartcmp_list_all_business_groups" in skill_text
    assert "datasource business-group" in skill_text
    assert "If datasource returns exactly one business group, use it silently" in skill_text
    assert "If datasource returns multiple business groups" in skill_text
