import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "resource-compliance"
    / "scripts"
    / "_analysis.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "test_resource_compliance_analysis_module",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_build_analysis_facts_extracts_core_fields():
    module = load_module()
    resource_record = {
        "resourceId": "db-1",
        "summary": {"name": "db-1", "resourceType": "cloudchef.nodes.Compute"},
        "resource": {
            "name": "db-1",
            "resourceType": "cloudchef.nodes.Compute",
            "componentType": "resource.iaas.machine.instance.abstract",
            "osType": "LINUX",
            "osDescription": "Ubuntu 20.04 LTS",
            "softwares": "MySQL 5.7.22",
            "properties": {"hostname": "db-1.corp"},
            "extensibleProperties": {"RuntimeProperties": {"version1": "5.7"}},
        },
        "details": {"kernel": "5.15.0", "mysqlVersion": "5.7.22"},
    }

    facts = module.build_analysis_facts(resource_record)

    assert facts["resourceId"] == "db-1"
    assert facts["resourceName"] == "db-1"
    assert facts["resourceType"] == "cloudchef.nodes.Compute"
    assert facts["osDescription"] == "Ubuntu 20.04 LTS"
    assert facts["softwares"] == "MySQL 5.7.22"
    assert facts["details"]["mysqlVersion"] == "5.7.22"
    assert facts["extensibleProperties"]["RuntimeProperties"]["version1"] == "5.7"


def test_builds_mysql_finding_from_version_and_external_check():
    module = load_module()
    facts = {
        "resourceId": "db-1",
        "resourceName": "mysql-prod-01",
        "resourceType": "cloudchef.nodes.Compute",
        "componentType": "resource.iaas.machine.instance.abstract",
        "osType": "LINUX",
        "osDescription": "CentOS 7.9",
        "softwares": "MySQL 5.7.22",
        "details": {},
        "properties": {},
    }

    result = module.analyze_resource_facts(
        facts,
        external_checker=lambda product, version: {
            "status": "unsupported",
            "summary": f"{product} {version} is beyond standard support.",
            "links": ["https://example.invalid/mysql-support"],
        },
    )

    assert result["summary"]["overallCompliance"] == "non_compliant"
    assert result["findings"][0]["category"] == "mysql_lifecycle"
    assert result["findings"][0]["status"] == "non_compliant"
    assert result["findings"][0]["sourceLinks"] == ["https://example.invalid/mysql-support"]


def test_builds_linux_finding_with_supported_version():
    module = load_module()
    facts = {
        "resourceId": "vm-1",
        "resourceName": "ubuntu-01",
        "resourceType": "cloudchef.nodes.Compute",
        "componentType": "resource.iaas.machine.instance.abstract",
        "osType": "LINUX",
        "osDescription": "Ubuntu 22.04.3 LTS",
        "softwares": "",
        "details": {"kernel": "6.5.0"},
        "properties": {},
    }

    result = module.analyze_resource_facts(
        facts,
        external_checker=lambda product, version: {
            "status": "supported",
            "summary": f"{product} {version} is in support.",
            "links": ["https://example.invalid/ubuntu-support"],
        },
    )

    assert result["summary"]["overallCompliance"] == "compliant"
    assert result["findings"][0]["category"] == "linux_security"
    assert result["findings"][0]["status"] == "compliant"


def test_returns_needs_review_when_version_evidence_is_missing():
    module = load_module()
    facts = {
        "resourceId": "vm-2",
        "resourceName": "win-legacy",
        "resourceType": "cloudchef.nodes.Compute",
        "componentType": "resource.iaas.machine.instance.abstract",
        "osType": "WINDOWS",
        "osDescription": "Windows Server",
        "softwares": "",
        "details": {},
        "properties": {},
    }

    result = module.analyze_resource_facts(
        facts,
        external_checker=lambda product, version: {
            "status": "supported",
            "summary": "unused",
            "links": [],
        },
    )

    assert result["summary"]["overallCompliance"] == "needs_review"
    assert result["findings"][0]["category"] == "windows_patch"
    assert result["findings"][0]["status"] == "needs_review"
    assert result["findings"][0]["confidence"] == "low"


def test_degrades_when_external_validation_is_unavailable():
    module = load_module()
    facts = {
        "resourceId": "vm-3",
        "resourceName": "win-2016",
        "resourceType": "cloudchef.nodes.Compute",
        "componentType": "resource.iaas.machine.instance.abstract",
        "osType": "WINDOWS",
        "osDescription": "Windows Server 2016 Datacenter",
        "softwares": "",
        "details": {},
        "properties": {},
    }

    def failing_checker(product, version):
        raise RuntimeError(f"external validation unavailable for {product} {version}")

    result = module.analyze_resource_facts(facts, external_checker=failing_checker)

    assert result["summary"]["overallCompliance"] == "needs_review"
    assert result["summary"]["confidence"] == "low"
    assert any("external validation unavailable" in item for item in result["uncertainties"])
    assert result["findings"][0]["status"] == "needs_review"


def test_mysql_detection_can_use_nested_version_fields():
    module = load_module()
    facts = {
        "resourceId": "db-2",
        "resourceName": "MySQL_32_example",
        "resourceType": "resource.software.rds.mysql_32",
        "componentType": "resource.software.rds.mysql_32",
        "osType": "linux",
        "osDescription": "",
        "softwares": "",
        "details": {},
        "properties": {},
        "exts": {"customProperty": {"version1": "5.7"}},
        "extensibleProperties": {"RuntimeProperties": {"version1": "5.7"}},
    }

    result = module.analyze_resource_facts(
        facts,
        external_checker=lambda product, version: {
            "status": "unsupported",
            "summary": f"{product} {version} is unsupported.",
            "links": ["https://example.invalid/mysql-support"],
        },
    )

    assert result["findings"][0]["category"] == "mysql_lifecycle"
    assert result["findings"][0]["title"] == "MySQL 5.7"
    assert result["summary"]["overallCompliance"] == "non_compliant"


def test_ambiguous_centos_version_stays_needs_review():
    module = load_module()
    facts = {
        "resourceId": "vm-4",
        "resourceName": "centos-ambiguous",
        "resourceType": "cloudchef.nodes.Compute",
        "componentType": "resource.iaas.machine.instance.abstract",
        "osType": "LINUX",
        "osDescription": "CentOS 4/5 或更高版本 (64 位)",
        "softwares": "",
        "details": {},
        "properties": {},
    }

    result = module.analyze_resource_facts(
        facts,
        external_checker=lambda product, version: {
            "status": "supported",
            "summary": "unused",
            "links": [],
        },
    )

    assert result["findings"][0]["category"] == "linux_security"
    assert result["findings"][0]["status"] == "needs_review"
    assert result["findings"][0]["title"] == "Centos detected with unknown version"
