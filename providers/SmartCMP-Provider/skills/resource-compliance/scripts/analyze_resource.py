#!/usr/bin/env python3
"""Analyze one or more SmartCMP resources for compliance risk."""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

import requests

try:
    from _analysis import analyze_resource_facts, build_analysis_facts
except ImportError:
    import os

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _analysis import analyze_resource_facts, build_analysis_facts

try:
    from _common import require_config
except ImportError:
    import os

    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import require_config

try:
    from list_resource import load_resource_records, request_json
except ImportError:
    import os

    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from list_resource import load_resource_records, request_json  # type: ignore


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze one or more SmartCMP resources for compliance risk."
    )
    parser.add_argument("resource_ids", nargs="*")
    parser.add_argument("--trigger-source", default="user")
    parser.add_argument("--payload-json")
    return parser.parse_args(argv)


def normalize_request(args):
    if args.payload_json:
        payload = json.loads(args.payload_json)
        resource_ids = payload.get("resourceIds") or payload.get("resource_ids") or []
        trigger_source = payload.get("triggerSource") or payload.get("trigger_source") or args.trigger_source
        raw_metadata = payload.get("rawMetadata") or payload
    else:
        resource_ids = args.resource_ids
        trigger_source = args.trigger_source
        raw_metadata = {}

    resource_ids = [str(item) for item in resource_ids if str(item).strip()]
    if not resource_ids:
        raise ValueError("At least one resource ID is required.")

    return {
        "resourceIds": resource_ids,
        "triggerSource": trigger_source,
        "rawMetadata": raw_metadata,
    }


def load_resources(resource_ids):
    base_url, _, headers, _ = require_config()
    return load_resource_records(
        resource_ids,
        base_url=base_url,
        headers=headers,
        request_fn=request_json,
    )


def external_checker(product, version):
    product = (product or "").lower()
    if product == "mysql":
        return check_mysql_support(version)
    if product == "windows":
        return check_windows_support(version)
    if product == "ubuntu":
        return check_ubuntu_support(version)
    return {
        "status": "unknown",
        "summary": f"No built-in authoritative checker is available yet for {product} {version}.",
        "links": [],
        "checkedAt": _now_iso(),
    }


def check_mysql_support(version):
    url = "https://www.mysql.com/support/eol-notice.html"
    text = fetch_text(url)
    lowered = text.lower()
    checked_at = _now_iso()

    if version.startswith("5.7") and "mysql 5.7 is covered under oracle lifetime sustaining support" in lowered:
        return {
            "status": "unsupported",
            "summary": "MySQL 5.7 is covered under Oracle Sustaining Support, which indicates regular standard support has ended.",
            "links": [url],
            "checkedAt": checked_at,
        }
    if version.startswith("8.0") and "mysql 8.0" in lowered and "eol in april 2026" in lowered:
        return {
            "status": "warning",
            "summary": "MySQL 8.0 is called out by the official MySQL EOL notice and approaches platform lifecycle limits.",
            "links": [url],
            "checkedAt": checked_at,
        }
    if version.startswith("8.4") and "mysql" in lowered:
        return {
            "status": "supported",
            "summary": "Official MySQL support pages are reachable; review the exact 8.4 support terms in Oracle documentation.",
            "links": [url],
            "checkedAt": checked_at,
        }

    return {
        "status": "unknown",
        "summary": f"Official MySQL support pages were reachable, but no exact lifecycle match was parsed for version {version}.",
        "links": [url],
        "checkedAt": checked_at,
    }


def check_windows_support(version):
    normalized_version = version.lower().replace(" ", "-")
    url = f"https://learn.microsoft.com/en-us/lifecycle/products/windows-server-{normalized_version}"
    markdown = fetch_text(url, accept="text/markdown")
    checked_at = _now_iso()
    match = re.search(
        r"\|\s*Windows Server [^|]+\|\s*[^|]+\|\s*([^|]+)\|\s*([^|]+)\|",
        markdown,
        flags=re.IGNORECASE,
    )
    if not match:
        return {
            "status": "unknown",
            "summary": f"Microsoft lifecycle content was reachable for Windows Server {version}, but support dates could not be parsed automatically.",
            "links": [url],
            "checkedAt": checked_at,
        }

    mainstream_end = match.group(1).strip()
    extended_end = match.group(2).strip()
    is_extended_expired = _is_past_iso_datetime(extended_end)

    if is_extended_expired:
        return {
            "status": "unsupported",
            "summary": f"Microsoft lists Windows Server {version} Extended End Date as {extended_end}.",
            "links": [url],
            "checkedAt": checked_at,
        }

    return {
        "status": "warning",
        "summary": f"Microsoft lists Windows Server {version} Mainstream End Date as {mainstream_end} and Extended End Date as {extended_end}.",
        "links": [url],
        "checkedAt": checked_at,
    }


def check_ubuntu_support(version):
    url = "https://ubuntu.com/about/release-cycle"
    text = fetch_text(url)
    checked_at = _now_iso()
    release_pattern = rf'"release":\s*"{re.escape(version)}(?:\s+LTS)?"'
    if not re.search(release_pattern, text, flags=re.IGNORECASE):
        return {
            "status": "unknown",
            "summary": f"Canonical release-cycle data was reachable, but Ubuntu {version} was not matched automatically.",
            "links": [url],
            "checkedAt": checked_at,
        }

    support_match = re.search(
        rf'"release":\s*"{re.escape(version)}(?:\s+LTS)?"[\s\S]{{0,1200}}?"supported":\s*\{{[\s\S]{{0,200}}?"raw":\s*"([^"]+)"',
        text,
        flags=re.IGNORECASE,
    )
    pro_match = re.search(
        rf'"release":\s*"{re.escape(version)}(?:\s+LTS)?"[\s\S]{{0,1200}}?"pro_supported":\s*\{{[\s\S]{{0,200}}?"raw":\s*"([^"]+)"',
        text,
        flags=re.IGNORECASE,
    )
    supported_until = support_match.group(1) if support_match else ""
    pro_until = pro_match.group(1) if pro_match else ""

    if supported_until and _is_past_date(supported_until):
        return {
            "status": "warning",
            "summary": f"Canonical lists Ubuntu {version} standard support until {supported_until}; check Ubuntu Pro/ESM coverage (listed as {pro_until or 'unknown'}).",
            "links": [url],
            "checkedAt": checked_at,
        }

    return {
        "status": "supported",
        "summary": f"Canonical release-cycle data lists Ubuntu {version} support through {supported_until or 'an available support window'}.",
        "links": [url],
        "checkedAt": checked_at,
    }


def fetch_text(url, accept="text/html"):
    headers = {
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        try:
            completed = subprocess.run(
                ["curl", "-LksS", "-H", f"Accept: {accept}", "-H", "Accept-Language: en-US,en;q=0.9", url],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(f"Failed to fetch external source: {url}") from exc
        if not completed.stdout:
            raise RuntimeError(f"External source returned no content: {url}")
        return completed.stdout


def build_failed_result(record):
    return {
        "resourceId": record.get("resourceId", ""),
        "resourceName": record.get("summary", {}).get("name")
        or record.get("resource", {}).get("name", ""),
        "resourceType": record.get("summary", {}).get("resourceType")
        or record.get("resource", {}).get("resourceType", ""),
        "analysisStatus": "fetch_failed",
        "observations": [],
        "findings": [],
        "summary": {
            "overallRisk": "medium",
            "overallCompliance": "needs_review",
            "confidence": "low",
        },
        "recommendations": ["Retry resource retrieval or inspect the resource directly in SmartCMP."],
        "uncertainties": record.get("errors", []),
    }


def render_output(payload):
    lines = [f"Analyzed {payload['analyzedCount']} resource(s)."]
    if payload["failedCount"]:
        lines.append(f"Failed to fully analyze {payload['failedCount']} resource(s).")
    lines.append("")

    for index, item in enumerate(payload["results"], start=1):
        lines.append(
            f"[{index}] {item.get('resourceName') or item.get('resourceId')} | "
            f"{item['summary']['overallCompliance']} | "
            f"confidence={item['summary']['confidence']}"
        )

    lines.extend(
        [
            "",
            "##RESOURCE_COMPLIANCE_START##",
            json.dumps(payload, ensure_ascii=False),
            "##RESOURCE_COMPLIANCE_END##",
        ]
    )
    return "\n".join(lines)


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_past_iso_datetime(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt.astimezone(timezone.utc) < datetime.now(timezone.utc)


def _is_past_date(value):
    try:
        dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return dt < datetime.now(timezone.utc)


def main(argv=None) -> int:
    try:
        request = normalize_request(parse_args(argv))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    try:
        resource_records = load_resources(request["resourceIds"])
    except Exception as exc:  # pragma: no cover - provider/network failures surface at runtime
        print(f"[ERROR] {exc}")
        return 1

    results = []
    analyzed_count = 0
    failed_count = 0
    for record in resource_records:
        if record.get("fetchStatus") not in {"ok", "partial"}:
            results.append(build_failed_result(record))
            failed_count += 1
            continue

        facts = build_analysis_facts(record)
        result = analyze_resource_facts(facts, external_checker=external_checker)
        if record.get("errors"):
            result["uncertainties"].extend(record["errors"])
        results.append(result)
        analyzed_count += 1

    payload = {
        "triggerSource": request["triggerSource"],
        "requestedResourceIds": request["resourceIds"],
        "analyzedCount": analyzed_count,
        "failedCount": failed_count,
        "generatedAt": _now_iso(),
        "results": results,
    }

    print(render_output(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
