#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""
SmartCMP-Provider End-to-End Test Script

Usage:
    python run_e2e_tests.py
    python run_e2e_tests.py --url http://localhost/platform-api --cookie "YOUR_COOKIE"

All interactive prompts default to the first option.
"""
from __future__ import annotations

import os
import sys
import json
import re
import subprocess
import argparse
from pathlib import Path

# ============================================================================
# Configuration
# ============================================================================
SCRIPT_DIR = Path(__file__).parent
PROVIDER_ROOT = SCRIPT_DIR.parent

DEFAULT_URL = "http://localhost/platform-api"
DEFAULT_COOKIE = "JSESSIONID=BF8FE40B1F512880116C71ECA2C7C5E9; username=%E5%B9%B3%E5%8F%B0%E7%AE%A1%E7%90%86%E5%91%98; userId=d4153d41-10a7-470c-b21a-8cee6243672e; userLoginId=admin; useremail=%28AES%29qK2pKqGW5NjauE3iJehRGA%3D%3D; tenantname=%E9%BB%98%E8%AE%A4%E7%A7%9F%E6%88%B7; tenant_id=default; userLastLogin=2026-03-11+15%3A47%3A34; CloudChef-Authenticate=eyJhbGciOiJIUzI1NiJ9.eyJ0ZW5hbnRJZCI6ImRlZmF1bHQiLCJzdWIiOiJkNDE1M2Q0MS0xMGE3LTQ3MGMtYjIxYS04Y2VlNjI0MzY3MmUiLCJleHAiOjE3NzMyMTkwMjQsImlhdCI6MTc3MzIxNzIyNH0.in-ONhWQe89iRhbf9mN_KpGd8gQP91_13wSm9eK3y84; CloudChef-Authenticate-Refresh=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJkNDE1M2Q0MS0xMGE3LTQ3MGMtYjIxYS04Y2VlNjI0MzY3MmUiLCJleHAiOjE3NzMyMjQ0MjQsImlhdCI6MTc3MzIxNzIyNH0.yRwb8PfdjPJ9hVknC2Kd2lUc3_cHdW64jas2A15mWBo"

LIVE_ENV_VARS = (
    "CMP_COOKIE",
    "CMP_USERNAME",
    "CMP_PASSWORD",
    "CMP_AUTH_URL",
    "ATLASCLAW_PROVIDER_CONFIG",
    "ATLASCLAW_COOKIES",
)
EXECUTE_FIX_E2E_ENV = "SMARTCMP_ENABLE_EXECUTE_FIX_E2E"
LIVE_SMOKE_AVAILABLE = False

# Test results
test_results = {"passed": 0, "failed": 0, "skipped": 0, "details": []}


# ============================================================================
# Helper Functions
# ============================================================================
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"
    RESET = "\033[0m"


def print_header(title: str):
    print(f"\n{Colors.CYAN}{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}{Colors.RESET}")


def print_result(test_name: str, success: bool, message: str = ""):
    global test_results
    status = "[PASS]" if success else "[FAIL]"
    color = Colors.GREEN if success else Colors.RED
    
    print(f"{color}{status}{Colors.RESET} {test_name}")
    if message:
        print(f"       {Colors.GRAY}{message}{Colors.RESET}")
    
    if success:
        test_results["passed"] += 1
    else:
        test_results["failed"] += 1
    
    test_results["details"].append({
        "name": test_name,
        "success": success,
        "message": message
    })


def print_skip(test_name: str, reason: str = ""):
    global test_results
    print(f"{Colors.YELLOW}[SKIP]{Colors.RESET} {test_name}")
    if reason:
        print(f"       {Colors.GRAY}{reason}{Colors.RESET}")
    test_results["skipped"] += 1


def run_script(script_path: str, args: list = None) -> tuple:
    """Run a Python script and return (success, output)."""
    full_path = PROVIDER_ROOT / script_path
    if not full_path.exists():
        return False, f"Script not found: {script_path}"
    
    cmd = [sys.executable, str(full_path)]
    if args:
        cmd.extend(args)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "CMP_URL": os.environ.get("CMP_URL", ""), 
                 "CMP_COOKIE": os.environ.get("CMP_COOKIE", "")}
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Script timeout"
    except Exception as e:
        return False, str(e)


def env_has_value(name: str) -> bool:
    """Return True when an environment variable is present and non-empty."""
    return bool(os.environ.get(name, "").strip())


def has_live_credentials() -> bool:
    """Detect whether live SmartCMP credentials/configuration are available."""
    return LIVE_SMOKE_AVAILABLE


def compute_live_smoke_available(cli_cookie: str | None) -> bool:
    """Detect whether the original invocation provided real live credentials."""
    if cli_cookie is not None and cli_cookie.strip():
        return True

    if env_has_value("CMP_COOKIE"):
        return True

    if env_has_value("CMP_USERNAME") and env_has_value("CMP_PASSWORD"):
        return True

    return any(env_has_value(name) for name in ("ATLASCLAW_PROVIDER_CONFIG", "ATLASCLAW_COOKIES"))


def resolve_url(cli_url: str | None) -> str:
    """Resolve the CMP URL from CLI, environment, or fallback defaults."""
    if cli_url is not None:
        return cli_url
    return os.environ.get("CMP_URL") or DEFAULT_URL


def resolve_cookie(cli_cookie: str | None) -> str:
    """Resolve the CMP cookie, preserving auto-login when credentials exist."""
    if cli_cookie is not None:
        return cli_cookie

    env_cookie = os.environ.get("CMP_COOKIE", "")
    if env_cookie.strip():
        return env_cookie

    if any(env_has_value(name) for name in ("CMP_USERNAME", "CMP_PASSWORD", "CMP_AUTH_URL")):
        return ""

    return DEFAULT_COOKIE


def extract_meta_json(output: str, start_tag: str, end_tag: str):
    """Extract JSON from META block in output."""
    pattern = f"{re.escape(start_tag)}\\s*([\\s\\S]*?)\\s*{re.escape(end_tag)}"
    match = re.search(pattern, output)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def extract_meta_list(meta_payload, list_key: str) -> list:
    """Normalize META payloads that may be a raw list or an envelope object."""
    if isinstance(meta_payload, list):
        return meta_payload
    if isinstance(meta_payload, dict):
        value = meta_payload.get(list_key)
        if isinstance(value, list):
            return value
    return []


def collect_skill_python_files() -> list[str]:
    """Return every Python file under skills/ as a provider-relative path."""
    skills_root = PROVIDER_ROOT / "skills"
    files: list[str] = []
    for py_file in skills_root.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        files.append(str(py_file.relative_to(PROVIDER_ROOT)))
    return sorted(files)


def collect_reference_markdown_files() -> list[str]:
    """Return every markdown file stored under a skill references/ directory."""
    skills_root = PROVIDER_ROOT / "skills"
    files: list[str] = []
    for md_file in skills_root.rglob("*.md"):
        if "references" not in md_file.parts:
            continue
        files.append(str(md_file.relative_to(PROVIDER_ROOT)))
    return sorted(files)


def extract_id_from_output(output: str) -> str:
    """Extract first ID from (id: xxx) pattern."""
    match = re.search(r"\(id:\s*([a-f0-9-]+)\)", output)
    return match.group(1) if match else None


def check_syntax(script_path: str) -> bool:
    """Check Python script syntax."""
    full_path = PROVIDER_ROOT / script_path
    if not full_path.exists():
        return False
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(full_path)],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except:
        return False


# ============================================================================
# Test Suite
# ============================================================================
def run_tests():
    global test_results
    
    # Banner
    print(f"""
{Colors.YELLOW}
  ____                       _    ____ __  __ ____  
 / ___| _ __ ___   __ _ _ __| |_ / ___|  \\/  |  _ \\ 
 \\___ \\| '_ ` _ \\ / _` | '__| __| |   | |\\/| | |_) |
  ___) | | | | | | (_| | |  | |_| |___| |  | |  __/ 
 |____/|_| |_| |_|\\__,_|_|   \\__|\\____|_|  |_|_|    
                                                    
  Provider E2E Test Suite (Python)
{Colors.RESET}""")
    
    print(f"{Colors.WHITE}Configuration:{Colors.RESET}")
    print(f"  {Colors.GRAY}CMP_URL:  {os.environ.get('CMP_URL', 'NOT SET')}{Colors.RESET}")
    cookie = os.environ.get('CMP_COOKIE', '')
    print(f"  {Colors.GRAY}Cookie:   {cookie[:50]}...{Colors.RESET}" if len(cookie) > 50 else f"  {Colors.GRAY}Cookie:   {cookie}{Colors.RESET}")
    print(f"  {Colors.GRAY}Provider: {PROVIDER_ROOT}{Colors.RESET}")

    # -------------------------------------------------------------------------
    # Test 1: Environment & Syntax Check
    # -------------------------------------------------------------------------
    print_header("1. Environment & Syntax Check")
    
    # Check Python
    print_result("Python Available", True, f"Python {sys.version.split()[0]}")
    
    # Syntax check for all scripts
    scripts = collect_skill_python_files()
    syntax_failures = [script for script in scripts if not check_syntax(script)]
    syntax_ok = not syntax_failures
    syntax_message = f"Checked {len(scripts)} files"
    if syntax_failures:
        syntax_message = "Failed: " + ", ".join(syntax_failures[:5])
        if len(syntax_failures) > 5:
            syntax_message += f" (+{len(syntax_failures) - 5} more)"
    print_result(f"All Scripts Syntax Check ({len(scripts)} files)", syntax_ok, syntax_message)

    # -------------------------------------------------------------------------
    # Test 2: Datasource Skill Tests
    # -------------------------------------------------------------------------
    print_header("2. Datasource Skill Tests")
    
    catalog_id = None
    
    # list_services.py
    success, output = run_script("skills/datasource/scripts/list_services.py")
    print_result("list_services.py", success, f"Exit code: {0 if success else 1}")
    if success:
        meta = extract_meta_json(output, "##CATALOG_META_START##", "##CATALOG_META_END##")
        catalogs = extract_meta_list(meta, "catalogs")
        if catalogs:
            catalog_id = catalogs[0].get("id")
            print(
                f"       {Colors.GRAY}Found {len(catalogs)} catalog(s), using first: "
                f"{catalogs[0].get('name')}{Colors.RESET}"
            )

    success, output = run_script("skills/datasource/scripts/list_all_business_groups.py")
    print_result("list_all_business_groups.py", success, f"Exit code: {0 if success else 1}")

    success, output = run_script("skills/resource-pool/scripts/list_all_resource_pools.py")
    print_result("list_all_resource_pools.py", success, f"Exit code: {0 if success else 1}")

    success, output = run_script("skills/resource/scripts/list_all_resource.py")
    print_result("list_all_resource.py", success, f"Exit code: {0 if success else 1}")
    print_skip(
        "resource_detail.py",
        "Skipped by default because refresh-status may trigger a backend refresh and requires a known resource ID",
    )
    print_skip("operate_resource.py", "Skipped by default to avoid power-operation side effects")
    
    if not catalog_id:
        print_skip("catalog-driven follow-ups", "No catalogId available")

    # -------------------------------------------------------------------------
    # Test 3: Approval Skill Tests
    # -------------------------------------------------------------------------
    print_header("3. Approval Skill Tests")
    
    success, output = run_script("skills/approval/scripts/list_pending.py")
    print_result("list_pending.py", success, f"Exit code: {0 if success else 1}")
    if success:
        meta = extract_meta_json(output, "##APPROVAL_META_START##", "##APPROVAL_META_END##")
        if meta and len(meta) > 0:
            print(f"       {Colors.GRAY}Found {len(meta)} pending approval(s){Colors.RESET}")
        else:
            print(f"       {Colors.GRAY}No pending approvals found (this is OK){Colors.RESET}")
    
    print_skip("approve.py", "Skipped to avoid side effects")
    print_skip("reject.py", "Skipped to avoid side effects")

    # -------------------------------------------------------------------------
    # Test 4: Alarm Skill Tests
    # -------------------------------------------------------------------------
    print_header("4. Alarm Skill Tests")

    alert_id = None

    if not has_live_credentials():
        print_skip(
            "alarm live smoke",
            "No live credentials/config detected; syntax coverage is still enforced",
        )
    else:
        success, output = run_script("skills/alarm/scripts/list_alerts.py")
        print_result("list_alerts.py", success, f"Exit code: {0 if success else 1}")
        if success:
            meta = extract_meta_json(output, "##ALARM_META_START##", "##ALARM_META_END##")
            if meta and len(meta) > 0:
                alert_id = meta[0].get("alertId")
                print(f"       {Colors.GRAY}Found {len(meta)} alert(s), using first: {alert_id}{Colors.RESET}")
            else:
                print(f"       {Colors.GRAY}No live alerts found (analysis smoke skipped){Colors.RESET}")

        if alert_id:
            success, output = run_script("skills/alarm/scripts/analyze_alert.py", [alert_id])
            print_result("analyze_alert.py", success, f"Exit code: {0 if success else 1}")
            if success:
                meta = extract_meta_json(output, "##ALARM_ANALYSIS_START##", "##ALARM_ANALYSIS_END##")
                has_payload = isinstance(meta, dict) and "alert_ids" in meta and "assessment" in meta
                print_result(
                    "analyze_alert.py structured output",
                    has_payload,
                    "Structured analysis block available" if has_payload else "Missing analysis block",
                )
        else:
            print_skip("analyze_alert.py", "No live alertId available")

        print_skip("operate_alert.py", "Skipped by default to avoid side effects")

    # -------------------------------------------------------------------------
    # Test 5: Cost Optimization Skill Tests
    # -------------------------------------------------------------------------
    print_header("5. Cost Optimization Skill Tests")

    cost_recommendation_id = None
    execute_fix_enabled = os.environ.get(EXECUTE_FIX_E2E_ENV, "").strip() == "1"

    if not has_live_credentials():
        print_skip(
            "cost-optimization live smoke",
            "No live credentials/config detected; syntax coverage is still enforced",
        )
    else:
        success, output = run_script("skills/cost-optimization/scripts/list_recommendations.py")
        print_result("list_recommendations.py", success, f"Exit code: {0 if success else 1}")
        if success:
            meta = extract_meta_json(
                output,
                "##COST_RECOMMENDATION_META_START##",
                "##COST_RECOMMENDATION_META_END##",
            )
            if meta and len(meta) > 0:
                cost_recommendation_id = meta[0].get("violationId")
                print(
                    f"       {Colors.GRAY}Found {len(meta)} recommendation(s), using first: "
                    f"{meta[0].get('policyName') or meta[0].get('resourceName') or cost_recommendation_id}{Colors.RESET}"
                )
            else:
                print(f"       {Colors.GRAY}No recommendation id returned from list output{Colors.RESET}")

        if cost_recommendation_id:
            success, output = run_script(
                "skills/cost-optimization/scripts/analyze_recommendation.py",
                ["--id", cost_recommendation_id],
            )
            print_result("analyze_recommendation.py", success, f"Exit code: {0 if success else 1}")
            if success:
                analysis = extract_meta_json(output, "##COST_ANALYSIS_START##", "##COST_ANALYSIS_END##")
                if analysis:
                    print(
                        f"       {Colors.GRAY}Theme: {analysis.get('assessment', {}).get('optimizationTheme', 'unknown')}"
                        f"{Colors.RESET}"
                    )
        else:
            print_skip("analyze_recommendation.py", "No recommendation id available")

        if cost_recommendation_id:
            success, output = run_script(
                "skills/cost-optimization/scripts/track_execution.py",
                ["--id", cost_recommendation_id],
            )
            print_result("track_execution.py", success, f"Exit code: {0 if success else 1}")
        else:
            print_skip("track_execution.py", "No recommendation id available")

        if execute_fix_enabled:
            if cost_recommendation_id:
                success, output = run_script(
                    "skills/cost-optimization/scripts/execute_optimization.py",
                    ["--id", cost_recommendation_id],
                )
                print_result("execute_optimization.py", success, f"Exit code: {0 if success else 1}")
            else:
                print_skip("execute_optimization.py", "No recommendation id available")
        else:
            print_skip("execute_optimization.py", f"Set {EXECUTE_FIX_E2E_ENV}=1 to enable remediation smoke")

    # -------------------------------------------------------------------------
    # Test 6: Request Skill Tests
    # -------------------------------------------------------------------------
    print_header("6. Request Skill Tests")
    
    success, output = run_script("skills/request/scripts/submit.py", ["--help"])
    # --help returns exit code 0 or shows usage
    print_result("submit.py --help", "usage:" in output.lower() or success, "Help output available")

    # -------------------------------------------------------------------------
    # Test 7: SKILL.md Definition Validation
    # -------------------------------------------------------------------------
    print_header("7. SKILL.md Definition Validation")
    
    skill_dirs = [
        "skills/approval",
        "skills/alarm",
        "skills/datasource",
        "skills/request",
        "skills/preapproval-agent",
        "skills/request-decomposition-agent",
        "skills/resource",
        "skills/resource-pool",
        "skills/cost-optimization",
    ]
    
    for skill_dir in skill_dirs:
        skill_path = PROVIDER_ROOT / skill_dir / "SKILL.md"
        skill_name = Path(skill_dir).name
        
        if skill_path.exists():
            content = skill_path.read_text(encoding="utf-8")
            has_name = "name:" in content
            has_desc = "description:" in content
            print_result(f"{skill_name}/SKILL.md", has_name and has_desc, "Valid structure" if has_name and has_desc else "Missing name or description")
        else:
            print_result(f"{skill_name}/SKILL.md", False, "File not found")

    # -------------------------------------------------------------------------
    # Test 8: Reference Files Validation
    # -------------------------------------------------------------------------
    print_header("8. Reference Files Validation")
    
    ref_files = collect_reference_markdown_files()
    
    for ref in ref_files:
        full_path = PROVIDER_ROOT / ref
        print_result(ref, full_path.exists())

    # -------------------------------------------------------------------------
    # Test Summary
    # -------------------------------------------------------------------------
    print(f"\n{Colors.CYAN}{'=' * 70}")
    print("  TEST SUMMARY")
    print(f"{'=' * 70}{Colors.RESET}\n")
    
    total = test_results["passed"] + test_results["failed"]
    pass_rate = (test_results["passed"] / total * 100) if total > 0 else 0
    
    print(f"  {Colors.GREEN}Passed:  {test_results['passed']}{Colors.RESET}")
    print(f"  {Colors.RED}Failed:  {test_results['failed']}{Colors.RESET}")
    print(f"  {Colors.YELLOW}Skipped: {test_results['skipped']}{Colors.RESET}")
    print(f"  {Colors.WHITE}Total:   {total}{Colors.RESET}")
    print()
    
    rate_color = Colors.GREEN if pass_rate >= 80 else (Colors.YELLOW if pass_rate >= 60 else Colors.RED)
    print(f"  {rate_color}Pass Rate: {pass_rate:.1f}%{Colors.RESET}\n")
    
    # List failed tests
    if test_results["failed"] > 0:
        print(f"  {Colors.RED}Failed Tests:{Colors.RESET}")
        for detail in test_results["details"]:
            if not detail["success"]:
                print(f"    - {detail['name']}: {detail['message']}")
        print()
    
    print(f"{Colors.CYAN}{'=' * 70}{Colors.RESET}\n")
    
    return 0 if test_results["failed"] == 0 else 1


# ============================================================================
# Main
# ============================================================================
def main():
    global LIVE_SMOKE_AVAILABLE

    parser = argparse.ArgumentParser(description="SmartCMP-Provider E2E Test Suite")
    parser.add_argument("--url", default=None, help="CMP API URL")
    parser.add_argument("--auth-url", default="", help="Optional explicit CMP auth URL")
    parser.add_argument("--cookie", default=None, help="CMP Cookie string")
    args = parser.parse_args()

    # Compute live-smoke eligibility before default-cookie fallback mutates env.
    LIVE_SMOKE_AVAILABLE = compute_live_smoke_available(args.cookie)

    # Set environment variables
    os.environ["CMP_URL"] = resolve_url(args.url)
    os.environ["CMP_COOKIE"] = resolve_cookie(args.cookie)
    if args.auth_url:
        os.environ["CMP_AUTH_URL"] = args.auth_url

    exit_code = run_tests()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
