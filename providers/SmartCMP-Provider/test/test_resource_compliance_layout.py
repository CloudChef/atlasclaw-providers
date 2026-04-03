import importlib.util
import sys
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROVIDER_ROOT / "skills" / "resource-compliance"
SHARED_SCRIPTS = PROVIDER_ROOT / "skills" / "shared" / "scripts"


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


def test_resource_compliance_skill_layout_exists():
    expected_files = [
        "SKILL.md",
        "references/WORKFLOW.md",
        "scripts/_analysis.py",
        "scripts/analyze_resource.py",
    ]

    assert SKILL_ROOT.is_dir(), "resource-compliance skill directory should exist"
    for relative_path in expected_files:
        assert (SKILL_ROOT / relative_path).exists(), relative_path

    assert (SHARED_SCRIPTS / "list_resource.py").exists()


def test_datasource_skill_mentions_resource_lookup():
    skill_text = (PROVIDER_ROOT / "skills" / "datasource" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "list_resource.py" in skill_text
    assert "resource details" in skill_text.lower()

    provider_text = (PROVIDER_ROOT / "PROVIDER.md").read_text(encoding="utf-8")
    assert "resource-compliance" in provider_text

    readme_text = (PROVIDER_ROOT / "README.md").read_text(encoding="utf-8")
    assert "resource-compliance" in readme_text

    workflow_text = (
        PROVIDER_ROOT / "skills" / "datasource" / "references" / "WORKFLOW.md"
    ).read_text(encoding="utf-8")
    assert "list_resource.py" in workflow_text


def test_resource_compliance_scripts_import_cleanly():
    helper_module = load_module(
        "test_resource_compliance_analysis_module",
        SKILL_ROOT / "scripts" / "_analysis.py",
    )
    assert helper_module is not None

    entrypoint_module = load_module(
        "test_resource_compliance_entrypoint_module",
        SKILL_ROOT / "scripts" / "analyze_resource.py",
    )
    assert hasattr(entrypoint_module, "main")

    list_resource_module = load_module(
        "test_list_resource_module",
        SHARED_SCRIPTS / "list_resource.py",
    )
    assert hasattr(list_resource_module, "main")
