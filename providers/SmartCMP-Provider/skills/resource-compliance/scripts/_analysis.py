#!/usr/bin/env python3
"""Helpers for SmartCMP resource compliance analysis."""

import re


def build_analysis_facts(resource_record: dict) -> dict:
    """Extract a stable fact object from a resource record."""
    summary = resource_record.get("summary") or {}
    resource = resource_record.get("resource") or {}
    details = resource_record.get("details") or {}

    return {
        "resourceId": resource_record.get("resourceId", ""),
        "resourceName": resource.get("name") or summary.get("name", ""),
        "resourceType": resource.get("resourceType") or summary.get("resourceType", ""),
        "componentType": resource.get("componentType") or summary.get("componentType", ""),
        "osType": resource.get("osType") or summary.get("osType", ""),
        "osDescription": resource.get("osDescription") or summary.get("osDescription", ""),
        "softwares": resource.get("softwares") or summary.get("softwares", ""),
        "properties": resource.get("properties") or {},
        "details": details,
        "resourceInfo": resource.get("resourceInfo") or {},
        "extra": resource.get("extra") or {},
        "exts": resource.get("exts") or {},
        "extensibleProperties": resource.get("extensibleProperties") or {},
    }


def detect_mysql(facts: dict) -> dict | None:
    text = " ".join(_candidate_texts(facts)).lower()
    if "mysql" not in text:
        return None

    version = _extract_version(
        _candidate_texts(facts),
        [
            r"mysql(?:\s+server)?[^\d]{0,8}(\d+(?:\.\d+){1,2})",
            r"mysqlversion[^\d]{0,8}(\d+(?:\.\d+){1,2})",
            r"\bmysqlversion=(\d+(?:\.\d+){1,2})",
            r"\bversion1=(\d+(?:\.\d+){1,2})",
        ],
    )

    return {
        "category": "mysql_lifecycle",
        "product": "mysql",
        "version": version,
        "title": f"MySQL {version}" if version else "MySQL detected with unknown version",
        "evidence": [item for item in _candidate_texts(facts) if "mysql" in item.lower()],
        "recommendation": "Confirm the MySQL version and plan upgrade if support has ended.",
    }


def detect_windows(facts: dict) -> dict | None:
    text = " ".join(_candidate_texts(facts)).lower()
    if "windows" not in text and (facts.get("osType") or "").upper() != "WINDOWS":
        return None

    version = _extract_version(
        _candidate_texts(facts),
        [
            r"windows(?:\s+server)?\s+(\d{4}(?:\s+r2)?)",
            r"windows\s+(\d{2})",
        ],
    )

    return {
        "category": "windows_patch",
        "product": "windows",
        "version": version,
        "title": f"Windows {version}" if version else "Windows detected with unknown version",
        "evidence": [item for item in _candidate_texts(facts) if "windows" in item.lower()],
        "recommendation": "Verify lifecycle status and confirm current patch posture.",
    }


def detect_linux(facts: dict) -> dict | None:
    text = " ".join(_candidate_texts(facts)).lower()
    if not _looks_like_linux(facts, text):
        return None

    distro, version = _extract_linux_distribution_and_version(_candidate_texts(facts))
    title = "Linux detected with unknown distribution/version"
    if distro and version:
        title = f"{distro.title()} {version}"
    elif distro:
        title = f"{distro.title()} detected with unknown version"

    return {
        "category": "linux_security",
        "product": distro or "linux",
        "version": version,
        "title": title,
        "evidence": [item for item in _candidate_texts(facts) if _contains_linux_signal(item)],
        "recommendation": "Verify distro support window and confirm security patch currency.",
    }


def analyze_resource_facts(facts: dict, external_checker) -> dict:
    findings = []
    uncertainties = []
    recommendations = []
    observations = build_observations(facts)

    detectors = [detect_mysql(facts), detect_windows(facts), detect_linux(facts)]
    for detected in [item for item in detectors if item]:
        finding = build_finding(detected, external_checker, uncertainties)
        findings.append(finding)
        recommendations.append(finding["recommendation"])

    if not findings:
        findings.append(
            {
                "category": "coverage",
                "severity": "low",
                "status": "needs_review",
                "title": "No supported technology signature detected",
                "evidence": [],
                "reasoning": "The current resource data does not clearly identify MySQL, Windows, or a Linux distribution/version.",
                "recommendation": "Collect more detailed OS and software inventory from the resource.",
                "confidence": "low",
                "externalEvidence": "",
                "sourceLinks": [],
                "checkedAt": "",
                "inferenceNote": "No supported detection pattern matched the available facts.",
            }
        )
        uncertainties.append("No supported technology signature could be detected from the current resource facts.")

    summary = summarize_findings(findings)

    return {
        "resourceId": facts.get("resourceId", ""),
        "resourceName": facts.get("resourceName", ""),
        "resourceType": facts.get("resourceType", ""),
        "analysisStatus": "analyzed",
        "observations": observations,
        "findings": findings,
        "summary": summary,
        "recommendations": _dedupe(recommendations),
        "uncertainties": uncertainties,
    }


def summarize_findings(findings: list[dict]) -> dict:
    if any(item["status"] == "non_compliant" for item in findings):
        return {
            "overallRisk": "high",
            "overallCompliance": "non_compliant",
            "confidence": _overall_confidence(findings),
        }
    if any(item["status"] == "at_risk" for item in findings):
        return {
            "overallRisk": "medium",
            "overallCompliance": "at_risk",
            "confidence": _overall_confidence(findings),
        }
    if any(item["status"] == "needs_review" for item in findings):
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


def build_finding(detected: dict, external_checker, uncertainties: list[str]) -> dict:
    version = detected.get("version")
    checked_at = ""
    external_summary = ""
    source_links = []

    if not version:
        return {
            "category": detected["category"],
            "severity": "medium",
            "status": "needs_review",
            "title": detected["title"],
            "evidence": detected["evidence"],
            "reasoning": "The product was recognized but the version could not be determined from current resource facts.",
            "recommendation": detected["recommendation"],
            "confidence": "low",
            "externalEvidence": "",
            "sourceLinks": [],
            "checkedAt": "",
            "inferenceNote": "Version-specific validation was skipped because the version was not identifiable.",
        }

    try:
        external = external_checker(detected["product"], version)
    except RuntimeError as exc:
        uncertainties.append(str(exc))
        return {
            "category": detected["category"],
            "severity": "medium",
            "status": "needs_review",
            "title": detected["title"],
            "evidence": detected["evidence"],
            "reasoning": "The product and version were identified, but external validation was unavailable.",
            "recommendation": detected["recommendation"],
            "confidence": "low",
            "externalEvidence": "",
            "sourceLinks": [],
            "checkedAt": "",
            "inferenceNote": "External validation could not be completed; this is a conservative fallback assessment.",
        }

    checked_at = external.get("checkedAt", "")
    external_summary = external.get("summary", "")
    source_links = external.get("links", [])
    status = external.get("status", "unknown")

    mapped_status = "needs_review"
    severity = "medium"
    confidence = "medium"
    reasoning = external_summary or "External validation returned an inconclusive result."

    if status in {"unsupported", "eol", "vulnerable"}:
        mapped_status = "non_compliant"
        severity = "high"
        confidence = "high"
    elif status in {"warning", "at_risk"}:
        mapped_status = "at_risk"
        severity = "medium"
        confidence = "medium"
    elif status in {"supported", "patched", "ok"}:
        mapped_status = "compliant"
        severity = "low"
        confidence = "high"

    return {
        "category": detected["category"],
        "severity": severity,
        "status": mapped_status,
        "title": detected["title"],
        "evidence": detected["evidence"],
        "reasoning": reasoning,
        "recommendation": detected["recommendation"],
        "confidence": confidence,
        "externalEvidence": external_summary,
        "sourceLinks": source_links,
        "checkedAt": checked_at,
        "inferenceNote": f"Assessment based on detected {detected['product']} version {version}.",
    }


def build_observations(facts: dict) -> list[str]:
    observations = []
    for key in ("osType", "osDescription", "softwares"):
        value = facts.get(key)
        if value:
            observations.append(f"{key}={value}")
    if facts.get("details"):
        observations.append(f"details_keys={','.join(sorted(facts['details'].keys()))}")
    return observations


def _candidate_texts(facts: dict) -> list[str]:
    texts = []
    for key in ("resourceName", "osType", "osDescription", "softwares"):
        value = facts.get(key)
        if value:
            texts.append(str(value))

    for mapping_key in ("properties", "details", "resourceInfo", "extra", "exts", "extensibleProperties"):
        mapping = facts.get(mapping_key) or {}
        texts.extend(_flatten_mapping(mapping, prefix=""))

    return texts


def _extract_version(texts: list[str], patterns: list[str]) -> str | None:
    for text in texts:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return None


def _looks_like_linux(facts: dict, text: str) -> bool:
    if (facts.get("osType") or "").upper() == "LINUX":
        return True
    return any(token in text for token in ("linux", "ubuntu", "centos", "debian", "red hat", "rhel", "rocky", "alma"))


def _extract_linux_distribution_and_version(texts: list[str]) -> tuple[str | None, str | None]:
    patterns = [
        ("ubuntu", r"ubuntu\s+(\d+(?:\.\d+){1,2})(?!/)"),
        ("centos", r"centos\s+(\d+(?:\.\d+)*)(?!/)"),
        ("debian", r"debian\s+(\d+(?:\.\d+)*)(?!/)"),
        ("rocky", r"rocky(?:\s+linux)?\s+(\d+(?:\.\d+)*)(?!/)"),
        ("almalinux", r"alma(?:linux)?\s+(\d+(?:\.\d+)*)(?!/)"),
        ("rhel", r"(?:red hat enterprise linux|rhel)\s+(\d+(?:\.\d+)*)(?!/)"),
    ]
    for text in texts:
        lower_text = text.lower()
        if re.search(r"centos\s+\d+/\d+", lower_text):
            return ("centos", None)
        for distro, pattern in patterns:
            match = re.search(pattern, lower_text, flags=re.IGNORECASE)
            if match:
                return distro, match.group(1)
    return ("linux", None) if any(_contains_linux_signal(text) for text in texts) else (None, None)


def _contains_linux_signal(text: str) -> bool:
    lower_text = text.lower()
    return any(token in lower_text for token in ("linux", "ubuntu", "centos", "debian", "red hat", "rhel", "rocky", "alma"))


def _overall_confidence(findings: list[dict]) -> str:
    if findings and all(item["confidence"] == "high" for item in findings):
        return "high"
    if any(item["confidence"] == "low" for item in findings):
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


def _flatten_mapping(value, prefix: str) -> list[str]:
    texts = []
    if isinstance(value, dict):
        for key, nested in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            texts.extend(_flatten_mapping(nested, next_prefix))
        return texts
    if isinstance(value, list):
        for index, nested in enumerate(value):
            next_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            texts.extend(_flatten_mapping(nested, next_prefix))
        return texts
    if value is None:
        return texts
    label = prefix or "value"
    texts.append(f"{label}={value}")
    return texts
