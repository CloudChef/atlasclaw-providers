#!/usr/bin/env python3
"""Helpers for SmartCMP resource compliance analysis."""

import re
from typing import Optional


def build_analysis_facts(resource_record: dict) -> dict:
    """Legacy compatibility helper kept for existing call sites."""
    summary = resource_record.get("summary") or {}
    resource = resource_record.get("resource") or {}
    normalized = resource_record.get("normalized") or {}
    return {
        "resourceId": resource_record.get("resourceId", ""),
        "resourceName": resource.get("name") or summary.get("name", ""),
        "resourceType": resource.get("resourceType") or summary.get("resourceType", ""),
        "componentType": resource.get("componentType") or summary.get("componentType", ""),
        "osType": resource.get("osType") or summary.get("osType", ""),
        "osDescription": resource.get("osDescription") or summary.get("osDescription", ""),
        "softwares": resource.get("softwares") or summary.get("softwares", ""),
        "properties": resource.get("properties") or {},
        "details": resource_record.get("details") or {},
        "resourceInfo": resource.get("resourceInfo") or {},
        "extra": resource.get("extra") or {},
        "exts": resource.get("exts") or {},
        "extensibleProperties": resource.get("extensibleProperties") or {},
        "normalized": normalized,
    }


def analyze_resource_facts(facts: dict, external_checker) -> dict:
    """Legacy compatibility entrypoint that forwards to normalized analysis."""
    normalized = facts.get("normalized") or build_normalized_from_legacy_facts(facts)
    result = analyze_normalized_resource(normalized, external_checker=external_checker)
    return {
        "resourceId": facts.get("resourceId", ""),
        "resourceName": facts.get("resourceName", ""),
        "resourceType": facts.get("resourceType", ""),
        "type": result["type"],
        "properties": result["properties"],
        "analysisTargets": result["analysisTargets"],
        "analysisStatus": "analyzed",
        "findings": result["findings"],
        "summary": result["summary"],
        "recommendations": result["recommendations"],
        "uncertainties": result["uncertainties"],
    }


def analyze_normalized_resource(normalized: dict, external_checker) -> dict:
    resource_type = str(normalized.get("type") or "")
    properties = normalized.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}

    analysis_targets = route_analyzers(resource_type, properties)
    findings = []
    uncertainties = []

    for target in analysis_targets:
        findings.extend(
            run_analyzer(
                target,
                resource_type,
                properties,
                external_checker=external_checker,
                uncertainties=uncertainties,
            )
        )

    if not findings:
        findings.append(
            build_finding(
                technology="coverage",
                analyzer_type="coverage",
                finding_type="coverage",
                status="needs_review",
                severity="low",
                title="No analyzer route matched this resource type",
                evidence=[f"type={resource_type}"] if resource_type else [],
                recommendation="Collect richer resource properties or add a new analyzer route.",
                confidence="low",
                detected_from="type",
            )
        )
        uncertainties.append("No analyzer route matched the resource type.")

    return {
        "type": resource_type,
        "properties": properties,
        "analysisTargets": analysis_targets,
        "findings": findings,
        "summary": summarize_findings(findings),
        "recommendations": _dedupe([item.get("recommendation", "") for item in findings]),
        "uncertainties": _dedupe(uncertainties),
    }


def build_normalized_from_legacy_facts(facts: dict) -> dict:
    properties = {}
    merge_first_wins(
        properties,
        {
            "resourceName": facts.get("resourceName"),
            "resourceType": facts.get("resourceType"),
            "componentType": facts.get("componentType"),
            "osType": facts.get("osType"),
            "osDescription": facts.get("osDescription"),
            "softwares": facts.get("softwares"),
        },
    )
    merge_first_wins(properties, _simple_fields(facts.get("properties") or {}))
    merge_first_wins(properties, _simple_fields(facts.get("details") or {}))
    merge_first_wins(properties, _simple_fields(facts.get("resourceInfo") or {}))
    merge_first_wins(properties, _simple_fields(facts.get("extra") or {}))
    merge_first_wins(properties, _extract_runtime_properties_from_facts(facts))
    return {
        "type": facts.get("componentType") or facts.get("resourceType", ""),
        "properties": properties,
    }


def route_analyzers(resource_type: str, properties: dict) -> list[str]:
    lowered = resource_type.lower()
    targets = []

    software_routes = [
        ("tomcat", "software:tomcat"),
        ("mysql", "software:mysql"),
        ("postgresql", "software:postgresql"),
        ("postgres", "software:postgresql"),
        ("redis", "software:redis"),
        ("elasticsearch", "software:elasticsearch"),
        ("sqlserver", "software:sqlserver"),
        ("sql_server", "software:sqlserver"),
        ("mssql", "software:sqlserver"),
    ]
    for token, target in software_routes:
        if token in lowered:
            targets.append(target)
            break

    if "alicloud_oss" in lowered:
        targets.append("cloud:alicloud_oss_v2")

    if _looks_like_windows_type(lowered):
        targets.append("os:windows")
    elif _looks_like_linux_type(lowered):
        targets.append("os:linux")

    # Fallback routing when type is weak but key properties are strong.
    if not targets:
        os_type = str(properties.get("osType") or "").lower()
        if "windows" in os_type:
            targets.append("os:windows")
        elif "linux" in os_type:
            targets.append("os:linux")

    return _dedupe(targets)


def run_analyzer(target: str, resource_type: str, properties: dict, *, external_checker, uncertainties: list[str]) -> list[dict]:
    if target == "cloud:alicloud_oss_v2":
        return analyze_alicloud_oss(properties)
    if target == "os:linux":
        return analyze_linux(properties, external_checker=external_checker, uncertainties=uncertainties)
    if target == "os:windows":
        return analyze_windows(properties, external_checker=external_checker, uncertainties=uncertainties)

    if target.startswith("software:"):
        technology = target.split(":", 1)[1]
        return analyze_software(
            technology=technology,
            resource_type=resource_type,
            properties=properties,
            external_checker=external_checker,
            uncertainties=uncertainties,
        )

    return []


def analyze_software(technology: str, resource_type: str, properties: dict, *, external_checker, uncertainties: list[str]) -> list[dict]:
    version_key, version = extract_software_version(technology, properties)
    if not version:
        return [
            build_finding(
                technology=technology,
                analyzer_type="software",
                finding_type="lifecycle",
                status="needs_review",
                severity="medium",
                title=f"{technology.title()} detected but version is missing",
                evidence=[f"type={resource_type}"] if resource_type else [],
                recommendation=f"Collect explicit {technology} version evidence (softwareVersion/version).",
                confidence="low",
                detected_from="type+properties",
            )
        ]

    return [
        build_versioned_external_finding(
            technology=technology,
            analyzer_type="software",
            finding_type="lifecycle",
            version=version,
            evidence=[f"{version_key}={version}"] if version_key else [f"version={version}"],
            recommendation=f"Review {technology} support and patch guidance for version {version}.",
            external_checker=external_checker,
            uncertainties=uncertainties,
        )
    ]


def analyze_linux(properties: dict, *, external_checker, uncertainties: list[str]) -> list[dict]:
    distro, version = extract_linux_version(properties)
    if not version:
        return [
            build_finding(
                technology="linux",
                analyzer_type="os",
                finding_type="patch",
                status="needs_review",
                severity="medium",
                title="Linux resource detected but distro/version is incomplete",
                evidence=_evidence_from_keys(properties, ["osType", "osDescription", "kernel"]),
                recommendation="Collect distro and version fields for lifecycle and patch validation.",
                confidence="low",
                detected_from="type+properties",
            )
        ]

    return [
        build_versioned_external_finding(
            technology=distro or "linux",
            analyzer_type="os",
            finding_type="lifecycle",
            version=version,
            evidence=[f"osVersion={version}"],
            recommendation=f"Review {distro or 'linux'} support policy for version {version}.",
            external_checker=external_checker,
            uncertainties=uncertainties,
        )
    ]


def analyze_windows(properties: dict, *, external_checker, uncertainties: list[str]) -> list[dict]:
    version = extract_windows_version(properties)
    if not version:
        return [
            build_finding(
                technology="windows",
                analyzer_type="os",
                finding_type="patch",
                status="needs_review",
                severity="medium",
                title="Windows resource detected but version/build evidence is incomplete",
                evidence=_evidence_from_keys(properties, ["osType", "osDescription", "build", "kb"]),
                recommendation="Collect Windows version/build/KB details for patch validation.",
                confidence="low",
                detected_from="type+properties",
            )
        ]

    if _looks_like_windows_client(properties, version):
        return [
            build_finding(
                technology="windows",
                analyzer_type="os",
                finding_type="patch",
                status="needs_review",
                severity="medium",
                title=f"Windows {version}",
                evidence=_evidence_from_keys(properties, ["osType", "osDescription", "build", "kb"]),
                recommendation="Collect Windows build/KB details or add a client lifecycle source adapter for authoritative validation.",
                confidence="low",
                detected_from="type+properties",
            )
        ]

    return [
        build_versioned_external_finding(
            technology="windows",
            analyzer_type="os",
            finding_type="lifecycle",
            version=version,
            evidence=[f"windowsVersion={version}"],
            recommendation=f"Review Microsoft lifecycle and update status for Windows {version}.",
            external_checker=external_checker,
            uncertainties=uncertainties,
        )
    ]


def analyze_alicloud_oss(properties: dict) -> list[dict]:
    findings = []
    public_access = str(
        properties.get("publicAccess")
        or properties.get("public_access")
        or properties.get("permission")
        or ""
    ).lower()
    encryption = str(
        properties.get("encryptionAlgorithm")
        or properties.get("encryption_algorithm")
        or ""
    ).strip()
    monitor_enabled = properties.get("monitorEnabled")

    if public_access and any(token in public_access for token in ("public", "read", "rw")) and "private" not in public_access:
        findings.append(
            build_finding(
                technology="alicloud_oss_v2",
                analyzer_type="cloud",
                finding_type="exposure",
                status="non_compliant",
                severity="high",
                title="OSS bucket may be publicly accessible",
                evidence=[f"publicAccess={public_access}"],
                recommendation="Set bucket ACL/policy to private and validate external access controls.",
                confidence="high",
                detected_from="properties",
            )
        )

    if not encryption:
        findings.append(
            build_finding(
                technology="alicloud_oss_v2",
                analyzer_type="cloud",
                finding_type="configuration",
                status="at_risk",
                severity="medium",
                title="OSS encryption configuration is missing",
                evidence=_evidence_from_keys(properties, ["encryptionAlgorithm", "encryption_algorithm"]),
                recommendation="Enable at-rest encryption for OSS buckets.",
                confidence="medium",
                detected_from="properties",
            )
        )

    if monitor_enabled is False:
        findings.append(
            build_finding(
                technology="alicloud_oss_v2",
                analyzer_type="cloud",
                finding_type="coverage",
                status="needs_review",
                severity="low",
                title="Monitoring is disabled for OSS resource",
                evidence=["monitorEnabled=False"],
                recommendation="Enable monitoring and alerting for OSS operations and exposure changes.",
                confidence="medium",
                detected_from="properties",
            )
        )

    if not findings:
        findings.append(
            build_finding(
                technology="alicloud_oss_v2",
                analyzer_type="cloud",
                finding_type="coverage",
                status="compliant",
                severity="low",
                title="No obvious OSS configuration risk detected from current properties",
                evidence=_evidence_from_keys(properties, ["publicAccess", "permission", "encryptionAlgorithm"]),
                recommendation="Continue periodic OSS posture validation.",
                confidence="medium",
                detected_from="properties",
            )
        )
    return findings


def build_versioned_external_finding(
    *,
    technology: str,
    analyzer_type: str,
    finding_type: str,
    version: str,
    evidence: list[str],
    recommendation: str,
    external_checker,
    uncertainties: list[str],
) -> dict:
    try:
        external = external_checker(technology, version)
    except RuntimeError as exc:
        uncertainties.append(str(exc))
        return build_finding(
            technology=technology,
            analyzer_type=analyzer_type,
            finding_type=finding_type,
            status="needs_review",
            severity="medium",
            title=f"{technology.title()} {version} detected but external validation is unavailable",
            evidence=evidence,
            recommendation=recommendation,
            confidence="low",
            detected_from="type+properties",
        )

    status, severity, confidence = map_external_status(external.get("status", "unknown"))
    summary = external.get("summary", "")
    return build_finding(
        technology=technology,
        analyzer_type=analyzer_type,
        finding_type=finding_type,
        status=status,
        severity=severity,
        title=f"{technology.title()} {version}",
        evidence=evidence,
        external_evidence=summary,
        source_links=external.get("links", []) or [],
        recommendation=recommendation,
        confidence=confidence,
        checked_at=external.get("checkedAt", ""),
        detected_from="type+properties",
    )


def build_finding(
    *,
    technology: str,
    analyzer_type: str,
    finding_type: str,
    status: str,
    severity: str,
    title: str,
    evidence: list[str],
    recommendation: str,
    confidence: str,
    detected_from: str,
    external_evidence: str = "",
    source_links: Optional[list[str]] = None,
    checked_at: str = "",
) -> dict:
    return {
        "technology": technology,
        "analyzerType": analyzer_type,
        "findingType": finding_type,
        "status": status,
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "externalEvidence": external_evidence,
        "sourceLinks": source_links or [],
        "recommendation": recommendation,
        "confidence": confidence,
        "checkedAt": checked_at,
        "detectedFrom": detected_from,
    }


def summarize_findings(findings: list[dict]) -> dict:
    statuses = {item.get("status", "") for item in findings}
    if statuses & {"non_compliant", "confirmed_vulnerable", "potentially_vulnerable"}:
        return {
            "overallRisk": "high",
            "overallCompliance": "non_compliant",
            "confidence": _overall_confidence(findings),
        }
    if "at_risk" in statuses:
        return {
            "overallRisk": "medium",
            "overallCompliance": "at_risk",
            "confidence": _overall_confidence(findings),
        }
    if "needs_review" in statuses:
        return {
            "overallRisk": "medium",
            "overallCompliance": "needs_review",
            "confidence": _overall_confidence(findings),
        }
    return {
        "overallRisk": "low",
        "overallCompliance": "compliant",
        "confidence": _overall_confidence(findings),
    }


def map_external_status(external_status: str) -> tuple[str, str, str]:
    status = (external_status or "").lower()
    if status in {"unsupported", "eol", "vulnerable"}:
        return "non_compliant", "high", "high"
    if status in {"warning", "at_risk"}:
        return "at_risk", "medium", "medium"
    if status in {"patched"}:
        return "patched", "low", "high"
    if status in {"supported", "ok"}:
        return "compliant", "low", "high"
    return "needs_review", "medium", "low"


def extract_version(properties: dict) -> Optional[str]:
    _, version = extract_version_with_source(
        properties,
        [
            "softwareVersion",
            "version",
            "productVersion",
            "mysqlVersion",
            "postgresVersion",
            "redisVersion",
            "elasticsearchVersion",
            "sqlServerVersion",
            "build",
        ],
    )
    return version


def merge_first_wins(target: dict, source: dict) -> None:
    for key, value in source.items():
        if not key:
            continue
        if key in target:
            continue
        if value in (None, ""):
            continue
        target[key] = value


def _simple_fields(mapping: dict) -> dict:
    if not isinstance(mapping, dict):
        return {}
    result = {}
    for key, value in mapping.items():
        if isinstance(value, (dict, list)):
            continue
        result[key] = value
    return result


def _extract_runtime_properties_from_facts(facts: dict) -> dict:
    runtime = {}
    exts = facts.get("exts") or {}
    if isinstance(exts, dict):
        merge_first_wins(runtime, _simple_fields(exts.get("customProperty") or {}))

    extensible = facts.get("extensibleProperties") or {}
    if isinstance(extensible, dict):
        merge_first_wins(runtime, _simple_fields(extensible.get("RuntimeProperties") or {}))
    return runtime


def extract_software_version(technology: str, properties: dict) -> tuple[Optional[str], Optional[str]]:
    technology_keys = {
        "mysql": [
            "mysqlVersion",
            "version1",
            "dbVersion",
            "version",
            "productVersion",
            "softwareVersion",
        ],
        "postgresql": [
            "postgresqlVersion",
            "postgresVersion",
            "dbVersion",
            "version",
            "productVersion",
            "softwareVersion",
        ],
        "redis": [
            "redisVersion",
            "version",
            "productVersion",
            "softwareVersion",
        ],
        "elasticsearch": [
            "elasticsearchVersion",
            "version",
            "productVersion",
            "softwareVersion",
        ],
        "sqlserver": [
            "sqlServerVersion",
            "mssqlVersion",
            "version",
            "productVersion",
            "softwareVersion",
            "build",
        ],
        "tomcat": [
            "softwareVersion",
            "version",
            "productVersion",
        ],
    }
    keys = technology_keys.get(technology, [])
    return extract_version_with_source(properties, keys)


def extract_version_with_source(properties: dict, candidate_keys: list[str]) -> tuple[Optional[str], Optional[str]]:
    ordered_keys = list(candidate_keys)
    for key in (
        "softwareVersion",
        "version",
        "productVersion",
        "mysqlVersion",
        "postgresVersion",
        "redisVersion",
        "elasticsearchVersion",
        "sqlServerVersion",
        "build",
    ):
        if key not in ordered_keys:
            ordered_keys.append(key)

    for key in ordered_keys:
        value = properties.get(key)
        if value not in (None, ""):
            return key, str(value).strip()

    soft = str(properties.get("softwares") or "")
    match = re.search(r"(\d+(?:\.\d+){1,3}(?:\.[A-Za-z0-9]+)?)", soft)
    if match:
        return "softwares", match.group(1)
    return None, None


def extract_linux_version(properties: dict) -> tuple[Optional[str], Optional[str]]:
    text = " ".join(
        str(properties.get(key) or "")
        for key in ("osDescription", "osVersion", "version", "softwareVersion", "kernel")
    )
    lowered = text.lower()
    ambiguous_distro = extract_ambiguous_linux_distro(lowered)
    if ambiguous_distro:
        return ambiguous_distro, None

    patterns = [
        ("ubuntu", r"ubuntu\s+(\d+(?:\.\d+)*)"),
        ("centos", r"centos\s+(\d+(?:\.\d+)*)"),
        ("debian", r"debian\s+(\d+(?:\.\d+)*)"),
        ("rhel", r"(?:rhel|red hat(?: enterprise linux)?)\s+(\d+(?:\.\d+)*)"),
        ("rocky", r"rocky(?:\s+linux)?\s+(\d+(?:\.\d+)*)"),
        ("almalinux", r"alma(?:linux)?\s+(\d+(?:\.\d+)*)"),
    ]
    for distro, pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            return distro, match.group(1)
    if "linux" in lowered:
        version = extract_version(properties)
        return "linux", version
    return None, None


def extract_windows_version(properties: dict) -> Optional[str]:
    for key in ("osVersion", "version", "softwareVersion", "build"):
        value = properties.get(key)
        if value not in (None, ""):
            parsed = parse_windows_version(str(value))
            if parsed:
                return parsed

    description = str(properties.get("osDescription") or "")
    return parse_windows_version(description)


def parse_windows_version(text: str) -> Optional[str]:
    match = re.search(
        r"windows(?:\s+server)?\s+(\d{4}(?:\s*r2)?|\d{1,2})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return None


def extract_ambiguous_linux_distro(text: str) -> Optional[str]:
    patterns = [
        ("centos", r"centos\s+\d+(?:\.\d+)?/\d+(?:\.\d+)?"),
        ("ubuntu", r"ubuntu\s+\d+(?:\.\d+)?/\d+(?:\.\d+)?"),
        ("debian", r"debian\s+\d+(?:\.\d+)?/\d+(?:\.\d+)?"),
        ("rocky", r"rocky(?:\s+linux)?\s+\d+(?:\.\d+)?/\d+(?:\.\d+)?"),
        ("almalinux", r"alma(?:linux)?\s+\d+(?:\.\d+)?/\d+(?:\.\d+)?"),
        ("rhel", r"(?:rhel|red hat(?: enterprise linux)?)\s+\d+(?:\.\d+)?/\d+(?:\.\d+)?"),
    ]
    for distro, pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return distro
    return None


def _looks_like_windows_client(properties: dict, version: str) -> bool:
    description = str(properties.get("osDescription") or "").lower()
    if "server" in description:
        return False
    return version in {"7", "8", "10", "11"}


def _looks_like_linux_type(lowered_type: str) -> bool:
    return ("linux" in lowered_type) and ("windows" not in lowered_type)


def _looks_like_windows_type(lowered_type: str) -> bool:
    return "windows" in lowered_type


def _evidence_from_keys(properties: dict, keys: list[str]) -> list[str]:
    evidence = []
    for key in keys:
        if key in properties and properties[key] not in (None, ""):
            evidence.append(f"{key}={properties[key]}")
    return evidence


def _overall_confidence(findings: list[dict]) -> str:
    if findings and all(item.get("confidence") == "high" for item in findings):
        return "high"
    if any(item.get("confidence") == "low" for item in findings):
        return "low"
    return "medium"


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
