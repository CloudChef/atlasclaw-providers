# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Render one SmartCMP Provider component definition for the current page."""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

try:
    from pydantic_ai import RunContext
except ImportError:  # Provider-only unit tests do not install the AtlasClaw runtime.
    RunContext = Any

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "shared", "scripts")
    ),
)

from _current_page_object import fetch_current_page_object  # noqa: E402
from smartcmp_provider.services.designers import project_component_definition  # noqa: E402


def _fence(content: str, language: str) -> str:
    longest = max(
        (len(match.group(0)) for match in re.finditer(r"`+", content)),
        default=0,
    )
    marker = "`" * max(3, longest + 1)
    return f"{marker}{language}\n{content}\n{marker}"


def _language(path: str, file_type: str) -> str:
    normalized_path = path.lower()
    normalized_type = file_type.lower()
    if normalized_path.endswith(".py") or normalized_type == "python":
        return "python"
    if normalized_path.endswith((".sh", ".bash")) or normalized_type in {
        "shell",
        "bash",
    }:
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


async def read_current_component_file(
    ctx: RunContext[Any],
    file_path: str = "",
) -> dict[str, Any]:
    """Render an exact current component file or request an exact selection."""

    try:
        payload = await fetch_current_page_object(
            ctx,
            expected_object_type="blueprint_component",
            api_collection="components",
        )
        component = project_component_definition(payload)
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}

    available = [
        {
            "path": item.path,
            "type": item.type,
            "mode": item.mode,
            "size": item.size,
        }
        for item in component.files
    ]
    requested_path = str(file_path or "").strip()
    if not component.files:
        return {
            "success": False,
            "error": "Current component has no readable files under scripts/.",
            "available_files": [],
        }
    if not requested_path and len(component.files) != 1:
        return {
            "success": True,
            "selection_required": True,
            "output": "\n".join(
                [
                    f"Current component: {component.name or component.object_id}",
                    f"Resource type: {component.resource_type}",
                    f"Component family: {component.component_family}",
                    "",
                    "Select one exact file_path from:",
                    "```json",
                    json.dumps(available, ensure_ascii=False, indent=2),
                    "```",
                ]
            ),
            "component": {
                "id": component.object_id,
                "resourceType": component.resource_type,
                "componentFamily": component.component_family,
                "files": available,
            },
        }

    selected = (
        component.files[0]
        if not requested_path and len(component.files) == 1
        else next(
            (
                item
                for item in component.files
                if item.path == requested_path
            ),
            None,
        )
    )
    if selected is None:
        return {
            "success": False,
            "error": (
                "file_path must exactly match a current component blueprint file."
            ),
            "available_files": available,
        }

    return {
        "success": True,
        "output": "\n".join(
            [
                f"Current component: {component.name or component.object_id}",
                f"Component ID: {component.object_id}",
                f"Resource type: {component.resource_type}",
                f"Component family: {component.component_family}",
                f"Selected file: {selected.path}",
                "",
                "All current component files:",
                "```json",
                json.dumps(available, ensure_ascii=False, indent=2),
                "```",
                "",
                "Complete selected file content:",
                _fence(selected.content, _language(selected.path, selected.type)),
            ]
        ),
        "component": {
            "id": component.object_id,
            "name": component.name,
            "resourceType": component.resource_type,
            "parentType": component.parent_type,
            "componentFamily": component.component_family,
            "files": available,
            "selectedFile": {
                "path": selected.path,
                "type": selected.type,
                "mode": selected.mode,
                "content": selected.content,
            },
        },
    }
