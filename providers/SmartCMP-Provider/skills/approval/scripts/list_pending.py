# -*- coding: utf-8 -*-
"""List pending approval items from SmartCMP with enhanced details.

Usage:
  python list_pending.py [--days N]

Arguments:
  --days N    Query approvals from last N days (default: 30)

Output:
  - Detailed list of pending approval items with priority analysis
  - ##APPROVAL_META_START## ... ##APPROVAL_META_END##
      JSON array with full structured info for agent processing

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_pending.py              # List last 30 days
  python list_pending.py --days 7     # List last 7 days

API Reference:
  GET /generic-request/current-activity-approval
"""
import sys
import json
import time
import requests
from datetime import datetime

# Import shared utilities (handles URL normalization, SSL warnings)
try:
    from _common import require_config
except ImportError:
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'scripts'))
    from _common import require_config

BASE_URL, AUTH_TOKEN, HEADERS, _ = require_config()

# -- Parse arguments -----------------------------------------------------------
days = 30
for i, arg in enumerate(sys.argv[1:]):
    if arg == "--days" and i + 2 < len(sys.argv):
        try:
            days = int(sys.argv[i + 2])
        except ValueError:
            pass

# Calculate time range (last N days)
now_ms = int(time.time() * 1000)
start_of_today = now_ms - (now_ms % 86400000)
start_at_min = start_of_today - (days * 86400000)
start_at_max = now_ms

headers = HEADERS

# -- Query pending approvals ---------------------------------------------------
url = f"{BASE_URL}/generic-request/current-activity-approval"
params = {
    "page": 1,
    "size": 50,
    "stage": "pending",
    "sort": "updatedDate,desc",
    "startAtMin": start_at_min,
    "startAtMax": start_at_max,
    "rangeField": "updatedDate",
    "states": "",
}

try:
    resp = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
    resp.raise_for_status()
    data = resp.json()
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Request failed: {e}")
    sys.exit(1)

# -- Extract list from response ------------------------------------------------
def _extract_list(d):
    if isinstance(d, list):
        return d
    for key in ("content", "data", "items", "result"):
        if isinstance(d.get(key), list):
            return d[key]
    return []

items = _extract_list(data) if isinstance(data, dict) else (data if isinstance(data, list) else [])
total = data.get("totalElements", len(items)) if isinstance(data, dict) else len(items)

if not items:
    print(f"No pending approvals found in the last {days} days.")
    sys.exit(0)

# -- Helper functions ----------------------------------------------------------
def format_timestamp(ts):
    """Convert timestamp to readable date string."""
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
        except:
            pass
    return str(ts) if ts else ""

def calculate_wait_hours(created_ts):
    """Calculate waiting hours since creation."""
    if isinstance(created_ts, (int, float)) and created_ts > 0:
        hours = (now_ms - created_ts) / 3600000
        return round(hours, 1)
    return 0

def extract_resource_specs(item):
    """Extract resource specification summary from request params."""
    specs = []
    activity = item.get("currentActivity") or {}
    params = activity.get("requestParams") or {}
    
    # Try to extract VM/Compute specs from various field patterns
    # Pattern 1: Direct fields with _ra_Compute_ prefix
    for key, val in params.items():
        if key.startswith("_ra_Compute_") or key.startswith("_ra_"):
            continue  # Skip internal fields
        if isinstance(val, dict):
            # Extract meaningful specs from nested dicts
            extract_from_dict(val, specs)
    
    # Pattern 2: resourceSpecs field (common in VM requests)
    resource_specs = params.get("resourceSpecs") or {}
    if isinstance(resource_specs, dict):
        for node_name, node_spec in resource_specs.items():
            if isinstance(node_spec, dict):
                extract_from_dict(node_spec, specs, node_name)
    
    # Pattern 3: extensibleParameters (common in various requests)
    ext_params = params.get("extensibleParameters") or {}
    if isinstance(ext_params, dict):
        for node_name, node_spec in ext_params.items():
            if isinstance(node_spec, dict):
                extract_from_dict(node_spec, specs, node_name)
    
    # Pattern 4: Look for specific compute fields
    compute_profile = params.get("_ra_Compute_compute_profile_id")
    if compute_profile:
        specs.append(f"计算配置: {compute_profile}")
    
    # Pattern 5: Check for quantity/count
    for key in ["quantity", "count", "instanceCount", "serverCount"]:
        if key in params and params[key]:
            specs.append(f"数量: {params[key]}")
            break
    
    # Deduplicate while preserving order
    seen = set()
    unique_specs = []
    for spec in specs:
        if spec not in seen:
            seen.add(spec)
            unique_specs.append(spec)
    
    return unique_specs[:6] if unique_specs else ["无详细规格"]

def extract_from_dict(d, specs, prefix=""):
    """Helper to extract specs from a dictionary."""
    prefix_str = f"{prefix}/" if prefix else ""
    
    def get_value(val):
        """Unwrap {value: x} pattern common in SmartCMP."""
        if isinstance(val, dict) and "value" in val:
            return val["value"]
        return val
    
    # CPU
    for key in ["cpu", "vcpu", "cpuCount", "cpu_count"]:
        if key in d:
            v = get_value(d[key])
            if v:
                specs.append(f"CPU: {v}核")
                break
    
    # Memory
    for key in ["memory", "ram", "memorySize", "memory_size"]:
        if key in d:
            v = get_value(d[key])
            if v:
                if isinstance(v, (int, float)) and v >= 1024:
                    v = f"{v/1024:.1f}GB"
                elif isinstance(v, (int, float)):
                    v = f"{v}MB"
                specs.append(f"内存: {v}")
                break
    
    # Disk/Storage
    for key in ["disk", "storage", "diskSize", "disk_size"]:
        if key in d:
            v = get_value(d[key])
            if v:
                specs.append(f"存储: {v}")
                break
    
    # Tags - only if there are real values
    if "tags" in d:
        tags_val = get_value(d["tags"])
        if isinstance(tags_val, dict) and tags_val:
            real_tags = {k: v for k, v in tags_val.items() if v is not None and v != ""}
            if real_tags:
                tag_str = ", ".join(f"{k}={v}" for k, v in list(real_tags.items())[:3])
                specs.append(f"标签: {tag_str}")
    
    # Type/Category
    for key in ["infra_type", "resourceType", "cloudEntryType"]:
        if key in d:
            v = get_value(d[key])
            if v and v != "vsphere":  # Skip common platform types
                specs.append(f"类型: {v}")
                break
    
    # Asset tag
    if "asset_tag" in d:
        v = get_value(d["asset_tag"])
        if v:
            specs.append(f"资产标签: {v}")

def extract_cost_info(item):
    """Extract cost/charge prediction info."""
    charge = item.get("chargePredictResult")
    if charge:
        if isinstance(charge, dict):
            total = charge.get("totalCost") or charge.get("cost") or charge.get("amount")
            if total:
                return f"¥{total}"
        return str(charge)
    return "未估算"

def calculate_priority(item):
    """Calculate priority score and label based on multiple factors."""
    score = 50  # Base score
    factors = []
    
    # Factor 1: Wait time (longer wait = higher priority)
    created = item.get("createdDate")
    wait_hours = calculate_wait_hours(created)
    if wait_hours > 72:
        score += 30
        factors.append("等待超3天")
    elif wait_hours > 24:
        score += 15
        factors.append("等待超1天")
    
    # Factor 2: SLA
    sla = item.get("sla")
    if sla:
        score += 20
        factors.append("有SLA")
    
    # Factor 3: Has cost estimate (larger deployments)
    if item.get("chargePredictResult"):
        score += 10
        factors.append("有成本预估")
    
    # Factor 4: Resource type keywords
    name = (item.get("name") or "").lower()
    catalog = (item.get("catalogName") or "").lower()
    combined = name + catalog
    
    high_priority_keywords = ["urgent", "紧急", "生产", "prod", "critical", "重要"]
    if any(kw in combined for kw in high_priority_keywords):
        score += 25
        factors.append("关键词标记")
    
    # Determine priority label
    if score >= 80:
        label = "高"
    elif score >= 60:
        label = "中"
    else:
        label = "低"
    
    return {"score": score, "label": label, "factors": factors}

def get_approval_step_name(item):
    """Get current approval step name."""
    activity = item.get("currentActivity") or {}
    step = activity.get("processStep") or {}
    return step.get("name") or "审批中"

def get_approver_info(item):
    """Extract current approver information."""
    activity = item.get("currentActivity") or {}
    assignments = activity.get("assignments") or []
    approvers = []
    for assign in assignments[:2]:
        approver = assign.get("approver") or {}
        name = approver.get("name") or approver.get("loginId") or ""
        if name:
            approvers.append(name)
    return ", ".join(approvers) if approvers else "待分配"

# -- Sort items by priority ----------------------------------------------------
for item in items:
    item["_priority"] = calculate_priority(item)

items.sort(key=lambda x: x["_priority"]["score"], reverse=True)

# -- User-visible list ---------------------------------------------------------
print(f"===============================================================")
print(f"  待审批列表 - 共 {total} 项 (按优先级排序)")
print(f"===============================================================\n")

for i, item in enumerate(items):
    # Basic info
    name = item.get("name") or item.get("requestName") or "N/A"
    workflow_id = item.get("workflowId") or ""
    catalog = item.get("catalogName") or item.get("resourceType") or item.get("type") or "通用请求"
    applicant = item.get("applicant") or item.get("requesterName") or item.get("createdByName") or "N/A"
    email = item.get("email") or ""
    description = item.get("description") or item.get("justification") or ""
    
    # Time info
    created_date = item.get("createdDate") or ""
    updated_date = item.get("updatedDate") or ""
    created_str = format_timestamp(created_date)
    updated_str = format_timestamp(updated_date)
    wait_hours = calculate_wait_hours(created_date)
    
    # Priority
    priority = item["_priority"]
    
    # Resource specs
    specs = extract_resource_specs(item)
    
    # Cost
    cost = extract_cost_info(item)
    
    # Approval info
    step_name = get_approval_step_name(item)
    approver = get_approver_info(item)
    
    # Print formatted output
    print(f"+- [{i+1}] {priority['label']} -----------------------------------------")
    print(f"|  名称: {name}")
    if workflow_id:
        print(f"|  工单号: {workflow_id}")
    print(f"|  类型: {catalog}")
    print(f"|")
    print(f"|  申请人: {applicant}" + (f" ({email})" if email else ""))
    if description:
        desc_short = description[:80] + "..." if len(description) > 80 else description
        print(f"|  说明: {desc_short}")
    print(f"|")
    print(f"|  创建时间: {created_str}")
    print(f"|  更新时间: {updated_str}")
    print(f"|  已等待: {wait_hours}小时")
    print(f"|")
    print(f"|  资源规格:")
    for spec in specs:
        print(f"|    - {spec}")
    print(f"|  预估成本: {cost}")
    print(f"|")
    print(f"|  审批阶段: {step_name}")
    print(f"|  当前审批人: {approver}")
    if priority["factors"]:
        print(f"|  优先因素: {', '.join(priority['factors'])}")
    print(f"+---------------------------------------------------------------\n")

# -- Summary -------------------------------------------------------------------
high_count = sum(1 for item in items if item["_priority"]["score"] >= 80)
mid_count = sum(1 for item in items if 60 <= item["_priority"]["score"] < 80)
low_count = sum(1 for item in items if item["_priority"]["score"] < 60)

print(f"===============================================================")
print(f"  优先级分布: 高 {high_count} | 中 {mid_count} | 低 {low_count}")
print(f"===============================================================\n")

# -- META block (agent reads silently) -----------------------------------------
# NOTE: The correct approval ID is in currentActivity.id, NOT the outer id field
meta = []
for i, item in enumerate(items):
    activity = item.get("currentActivity") or {}
    meta.append({
        "index": i + 1,
        "id": activity.get("id") or item.get("id") or "",
        "requestId": item.get("id") or "",
        "name": item.get("name") or item.get("requestName") or "",
        "workflowId": item.get("workflowId") or "",
        "catalogName": item.get("catalogName") or "",
        "applicant": item.get("applicant") or "",
        "email": item.get("email") or "",
        "description": item.get("description") or "",
        "createdDate": item.get("createdDate") or "",
        "updatedDate": item.get("updatedDate") or "",
        "waitHours": calculate_wait_hours(item.get("createdDate")),
        "priority": item["_priority"]["label"],
        "priorityScore": item["_priority"]["score"],
        "priorityFactors": item["_priority"]["factors"],
        "approvalStep": get_approval_step_name(item),
        "currentApprover": get_approver_info(item),
        "costEstimate": extract_cost_info(item),
        "resourceSpecs": extract_resource_specs(item),
        "processInstanceId": activity.get("processInstanceId") or "",
        "taskId": activity.get("taskId") or "",
    })

print("##APPROVAL_META_START##")
print(json.dumps(meta, ensure_ascii=False))
print("##APPROVAL_META_END##")
