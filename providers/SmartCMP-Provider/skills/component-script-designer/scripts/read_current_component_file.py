# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Read one saved file from the component bound to the current page Context."""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any


try:
    from pydantic_ai import RunContext
except ImportError:  # Provider-only unit tests do not install the Core runtime.
    RunContext = Any


sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "shared", "scripts")
    ),
)

from _current_page_object import (  # noqa: E402
    CurrentPageObjectError,
    fetch_current_page_object,
)


def _component_family(resource_type: str) -> str:
    normalized = str(resource_type or "").strip().lower()
    exporter_type = "resource.agent.monitoring_agent.prometheus_exporter"
    if normalized == exporter_type or normalized.startswith(f"{exporter_type}."):
        return "exporter"
    if normalized.startswith("resource.integration."):
        return "integration"
    if normalized.startswith("resource.software."):
        return "software"
    if normalized.startswith(
        ("resource.iaas.", "resource.paas.", "resource.caas.")
    ):
        return "resource"
    return ""


def _language(path: str, file_type: str) -> str:
    normalized_path = path.lower()
    normalized_type = file_type.lower()
    if normalized_path.endswith(".py") or normalized_type == "python":
        return "python"
    if normalized_path.endswith((".sh", ".bash")) or normalized_type in {"shell", "bash"}:
        return "bash"
    if normalized_path.endswith((".yml", ".yaml")) or normalized_type in {
        "yaml",
        "ansible",
    }:
        return "yaml"
    if normalized_path.endswith(".json") or normalized_type == "json":
        return "json"
    if normalized_path.endswith(".ps1") or normalized_type == "powershell":
        return "powershell"
    return "text"


def _fence(content: str, language: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", content)), default=0)
    marker = "`" * max(3, longest + 1)
    return f"{marker}{language}\n{content}\n{marker}"


def _script_path(value: Any) -> str:
    """Return one safe component script path, or an empty string."""
    path = str(value or "").strip()
    if (
        not path.startswith("scripts/")
        or path.startswith("/")
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        return ""
    return path


async def read_current_component_file(
    ctx: RunContext[Any],
    file_path: str = "",
) -> dict[str, Any]:
    """Return one exact current component file, or list files for exact selection."""
    try:
        payload = await fetch_current_page_object(
            ctx,
            expected_object_type="blueprint_component",
            api_collection="components",
        )
    except CurrentPageObjectError as exc:
        return {"success": False, "error": str(exc)}

    resource_type = str(payload.get("resourceType") or "").strip()
    family = _component_family(resource_type)
    if not family:
        return {
            "success": False,
            "error": (
                "Current component resourceType is not supported by the component "
                "script designer."
            ),
        }
    model = payload.get("model")
    model = model if isinstance(model, dict) else {}
    raw_files = model.get("blueprintFiles")
    files = [
        item
        for item in raw_files
        if isinstance(raw_files, list)
        and isinstance(item, dict)
        and _script_path(item.get("path"))
        and isinstance(item.get("content"), str)
    ] if isinstance(raw_files, list) else []
    available = [
        {
            "path": _script_path(item["path"]),
            "type": str(item.get("type") or ""),
            "mode": str(item.get("mode") or ""),
            "size": len(str(item["content"]).encode("utf-8")),
        }
        for item in files
    ]
    requested_path = str(file_path or "").strip()
    if not files:
        return {
            "success": False,
            "error": "Current component has no readable files under scripts/.",
            "available_files": [],
        }
    if not requested_path and len(files) != 1:
        return {
            "success": True,
            "selection_required": True,
            "output": "\n".join(
                [
                    f"Current component: {payload.get('name') or payload['id']}",
                    f"Resource type: {resource_type}",
                    f"Component family: {family}",
                    "",
                    "Select one exact file_path from:",
                    "```json",
                    json.dumps(available, ensure_ascii=False, indent=2),
                    "```",
                ]
            ),
            "component": {
                "id": payload["id"],
                "resourceType": resource_type,
                "componentFamily": family,
                "files": available,
            },
        }

    selected = (
        files[0]
        if not requested_path and len(files) == 1
        else next(
            (
                item
                for item in files
                if str(item.get("path") or "").strip() == requested_path
            ),
            None,
        )
    )
    if not isinstance(selected, dict):
        return {
            "success": False,
            "error": "file_path must exactly match a current component blueprint file.",
            "available_files": available,
        }

    selected_path = _script_path(selected["path"])
    selected_type = str(selected.get("type") or "")
    content = str(selected["content"])
    return {
        "success": True,
        "output": "\n".join(
            [
                f"Current component: {payload.get('name') or payload['id']}",
                f"Component ID: {payload['id']}",
                f"Resource type: {resource_type}",
                f"Component family: {family}",
                f"Selected file: {selected_path}",
                "",
                "All current component files:",
                "```json",
                json.dumps(available, ensure_ascii=False, indent=2),
                "```",
                "",
                "Complete selected file content:",
                _fence(content, _language(selected_path, selected_type)),
            ]
        ),
        "component": {
            "id": payload["id"],
            "name": str(payload.get("name") or ""),
            "resourceType": resource_type,
            "parentType": str(payload.get("parentType") or ""),
            "componentFamily": family,
            "files": available,
            "selectedFile": {
                "path": selected_path,
                "type": selected_type,
                "mode": str(selected.get("mode") or ""),
                "content": content,
            },
        },
    }
