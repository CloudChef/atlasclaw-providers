from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROVIDER_ROOT / "skills" / "cost-optimization"


def test_cost_optimization_skill_layout_exists():
    expected_files = [
        "SKILL.md",
        "references/WORKFLOW.md",
        "scripts/_cost_common.py",
        "scripts/_analysis.py",
        "scripts/list_recommendations.py",
        "scripts/analyze_recommendation.py",
        "scripts/execute_optimization.py",
        "scripts/track_execution.py",
    ]

    assert SKILL_ROOT.is_dir()
    for relative_path in expected_files:
        assert (SKILL_ROOT / relative_path).exists(), relative_path


def test_cost_optimization_skill_metadata_contains_required_keys():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert 'name: "cost-optimization"' in skill_text
    assert 'description: "SmartCMP cost optimization skill.' in skill_text
    assert 'provider_type: "smartcmp"' in skill_text
    assert "tool_list_name:" in skill_text
    assert "tool_analyze_name:" in skill_text
    assert "tool_execute_name:" in skill_text
    assert "tool_track_name:" in skill_text
