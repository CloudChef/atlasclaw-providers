import importlib.util
import sys
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROVIDER_ROOT / "skills" / "resource-power"


def load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def test_resource_power_skill_layout_exists():
    expected_files = [
        "SKILL.md",
        "references/WORKFLOW.md",
        "scripts/operate_resource_power.py",
    ]

    assert SKILL_ROOT.is_dir(), "resource-power skill directory should exist"
    for relative_path in expected_files:
        assert (SKILL_ROOT / relative_path).exists(), relative_path


def test_resource_power_skill_metadata_contains_required_keys():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert 'name: "resource-power"' in skill_text
    assert 'description: "SmartCMP cloud resource power operation skill.' in skill_text
    assert 'provider_type: "smartcmp"' in skill_text
    assert "tool_power_name:" in skill_text
    assert "tool_power_parameters:" in skill_text


def test_resource_power_entrypoint_imports_cleanly_and_docs_reference_skill():
    module = load_module(
        "test_resource_power_entrypoint_module",
        SKILL_ROOT / "scripts" / "operate_resource_power.py",
    )
    assert hasattr(module, "main")

    provider_text = (PROVIDER_ROOT / "PROVIDER.md").read_text(encoding="utf-8")
    assert "resource-power" in provider_text

    readme_text = (PROVIDER_ROOT / "README.md").read_text(encoding="utf-8")
    assert "resource-power" in readme_text
