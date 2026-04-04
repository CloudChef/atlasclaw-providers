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


def supported_checker(product, version):
    return {
        "status": "supported",
        "summary": f"{product} {version} is in support.",
        "links": [f"https://example.invalid/{product}"],
        "checkedAt": "2026-04-04T00:00:00Z",
    }


def test_routes_tomcat_by_component_type_and_emits_generic_finding():
    module = load_module()
    normalized = {
        "type": "resource.software.app.tomcat",
        "properties": {"softwareVersion": "9.0.0.M10", "port": 8080},
    }
    result = module.analyze_normalized_resource(normalized, external_checker=supported_checker)

    assert result["type"] == "resource.software.app.tomcat"
    assert result["analysisTargets"] == ["software:tomcat"]
    assert result["findings"][0]["technology"] == "tomcat"
    assert result["findings"][0]["analyzerType"] == "software"
    assert result["findings"][0]["findingType"] == "lifecycle"


def test_returns_coverage_when_no_analyzer_matches():
    module = load_module()
    result = module.analyze_normalized_resource(
        {"type": "resource.unknown.custom", "properties": {"name": "x"}},
        external_checker=supported_checker,
    )

    assert result["findings"][0]["findingType"] == "coverage"
    assert result["summary"]["overallCompliance"] == "needs_review"


def test_routes_supported_software_types():
    module = load_module()
    cases = [
        ("resource.software.db.mysql", "software:mysql", "mysql"),
        ("resource.software.db.postgresql", "software:postgresql", "postgresql"),
        ("resource.software.cache.redis", "software:redis", "redis"),
        ("resource.software.search.elasticsearch", "software:elasticsearch", "elasticsearch"),
        ("resource.software.db.sqlserver", "software:sqlserver", "sqlserver"),
    ]
    for resource_type, target, technology in cases:
        result = module.analyze_normalized_resource(
            {"type": resource_type, "properties": {"softwareVersion": "1.2.3"}},
            external_checker=supported_checker,
        )
        assert result["analysisTargets"] == [target]
        assert result["findings"][0]["technology"] == technology


def test_mysql_prefers_runtime_version_over_component_version():
    module = load_module()
    result = module.analyze_normalized_resource(
        {
            "type": "resource.software.rds.mysql_32",
            "properties": {
                "softwareVersion": "1.0",
                "version1": "5.7",
            },
        },
        external_checker=supported_checker,
    )

    assert result["analysisTargets"] == ["software:mysql"]
    assert result["findings"][0]["title"] == "Mysql 5.7"
    assert result["findings"][0]["evidence"] == ["version1=5.7"]


def test_legacy_facts_keep_nested_runtime_fields_for_mysql_analysis():
    module = load_module()
    record = {
        "resourceId": "db-legacy-1",
        "summary": {
            "name": "mysql-legacy",
            "resourceType": "cloudchef.nodes.Compute",
            "componentType": "resource.software.rds.mysql_32",
            "osType": "LINUX",
        },
        "resource": {
            "name": "mysql-legacy",
            "resourceType": "cloudchef.nodes.Compute",
            "componentType": "resource.software.rds.mysql_32",
            "osType": "LINUX",
            "properties": {"softwareVersion": "1.0"},
            "extensibleProperties": {"RuntimeProperties": {"version1": "5.7"}},
        },
        "details": {"hostname": "db-legacy-1"},
    }

    facts = module.build_analysis_facts(record)
    result = module.analyze_resource_facts(facts, external_checker=supported_checker)

    assert result["type"] == "resource.software.rds.mysql_32"
    assert result["analysisTargets"] == ["software:mysql"]
    assert result["properties"]["version1"] == "5.7"
    assert result["findings"][0]["evidence"] == ["version1=5.7"]


def test_software_without_version_degrades_to_needs_review():
    module = load_module()
    result = module.analyze_normalized_resource(
        {"type": "resource.software.db.postgresql", "properties": {"softwareName": "PostgreSQL"}},
        external_checker=supported_checker,
    )

    assert result["findings"][0]["status"] == "needs_review"
    assert result["summary"]["overallCompliance"] == "needs_review"


def test_routes_linux_as_first_class_os_target():
    module = load_module()
    result = module.analyze_normalized_resource(
        {
            "type": "resource.os.linux",
            "properties": {"osDescription": "Ubuntu 22.04.3 LTS", "osType": "LINUX"},
        },
        external_checker=supported_checker,
    )
    assert result["analysisTargets"] == ["os:linux"]
    assert result["findings"][0]["technology"] == "ubuntu"
    assert result["findings"][0]["analyzerType"] == "os"


def test_routes_windows_as_first_class_os_target():
    module = load_module()
    result = module.analyze_normalized_resource(
        {
            "type": "resource.os.windows",
            "properties": {"osDescription": "Windows Server 2016 Datacenter", "osType": "WINDOWS"},
        },
        external_checker=supported_checker,
    )
    assert result["analysisTargets"] == ["os:windows"]
    assert result["findings"][0]["technology"] == "windows"
    assert result["findings"][0]["analyzerType"] == "os"


def test_missing_windows_build_degrades_to_needs_review():
    module = load_module()
    result = module.analyze_normalized_resource(
        {"type": "resource.os.windows", "properties": {"osType": "WINDOWS"}},
        external_checker=supported_checker,
    )
    assert result["findings"][0]["status"] == "needs_review"


def test_windows_client_version_is_detected_but_kept_conservative():
    module = load_module()
    result = module.analyze_normalized_resource(
        {
            "type": "resource.iaas.machine.windows_instance.vsphere",
            "properties": {"osType": "WINDOWS", "osDescription": "Microsoft Windows 10 (64 位)"},
        },
        external_checker=supported_checker,
    )
    assert result["analysisTargets"] == ["os:windows"]
    assert result["findings"][0]["title"] == "Windows 10"
    assert result["findings"][0]["status"] == "needs_review"


def test_ambiguous_linux_version_does_not_collapse_to_first_number():
    module = load_module()
    result = module.analyze_normalized_resource(
        {
            "type": "resource.iaas.machine.instance.vsphere",
            "properties": {"osType": "LINUX", "osDescription": "CentOS 4/5 或更高版本 (64 位)"},
        },
        external_checker=supported_checker,
    )
    assert result["analysisTargets"] == ["os:linux"]
    assert result["findings"][0]["title"] == "Linux resource detected but distro/version is incomplete"
    assert result["findings"][0]["status"] == "needs_review"


def test_routes_alicloud_oss_cloud_analyzer():
    module = load_module()
    result = module.analyze_normalized_resource(
        {
            "type": "resource.iaas.storage.object.alicloud_oss_v2",
            "properties": {
                "publicAccess": "private",
                "encryptionAlgorithm": "",
                "monitorEnabled": False,
            },
        },
        external_checker=supported_checker,
    )

    assert result["analysisTargets"] == ["cloud:alicloud_oss_v2"]
    finding_types = {item["findingType"] for item in result["findings"]}
    assert "configuration" in finding_types
    assert "exposure" not in finding_types
