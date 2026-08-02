"""Focused SmartCMP Provider contracts for SmartCMP designer object reads."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

PROVIDER_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROVIDER_SRC) not in sys.path:
    sys.path.insert(0, str(PROVIDER_SRC))

from smartcmp_provider.auth.resolver import resolve_provided_request
from smartcmp_provider.models.forms import FormReadQuery
from smartcmp_provider.models.objects import ObjectIdQuery
from smartcmp_provider.services.designers import (
    read_component_definition,
    read_optimization_policy,
    read_script_definition,
)
from smartcmp_provider.services.forms import read_form
from smartcmp_provider.transport.client import SmartCmpClient

COMPONENT_ID = "010c8da0-9866-4b32-bbff-72f3d49efb4e"
POLICY_ID = "e3085cba-e8b9-4e6c-a65d-36331cdbe47d"
SCRIPT_ID = "3e045633-6ed6-4988-bddf-c7136d54e7de"
FORM_ID = "0897c154-3c46-414e-906e-2a7277f8def2"


def test_designer_reads_fetch_and_project_all_supported_objects() -> None:
    """Every designer projection must be callable without AtlasClaw Context."""

    payloads = {
        f"/platform-api/components/{COMPONENT_ID}": {
            "id": COMPONENT_ID,
            "name": "CMDB",
            "resourceType": "resource.integration.cmdb.example",
            "model": {
                "blueprintFiles": [
                    {
                        "path": "scripts/client.py",
                        "type": "PYTHON",
                        "content": "READY = True",
                    },
                    {
                        "path": "scripts/../secret.py",
                        "content": "UNSAFE = True",
                    },
                ]
            },
        },
        f"/platform-api/compliance-policies/{POLICY_ID}": {
            "id": POLICY_ID,
            "name": "Right-size VM",
            "category": "COST-OPTIMIZATION.MACHINE",
            "severity": "HIGH",
            "ruleContent": "return compliant",
        },
        f"/platform-api/scripts/{SCRIPT_ID}": {
            "id": SCRIPT_ID,
            "name": "check.py",
            "type": "PYTHON",
            "content": "def check():\n    return True",
        },
        f"/platform-api/forms/{FORM_ID}": {
            "id": FORM_ID,
            "name": "Request Form",
            "content": {
                "schema": {
                    "type": "object",
                    "widget": {"id": "object"},
                    "properties": {},
                    "fieldsets": [],
                },
                "model": {},
                "designMode": "schema",
            },
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=payloads[request.url.path],
            request=request,
        )

    request = resolve_provided_request(
        instance_name="cmp-test",
        base_url="https://cmp.example.com",
        subject="user-1",
        auth_type="cookie",
        credential_value="session-secret",
        trace_id="designer-read",
    )

    async def invoke():
        async with SmartCmpClient(
            request,
            transport=httpx.MockTransport(handler),
        ) as client:
            return (
                await read_component_definition(
                    client,
                    ObjectIdQuery(object_id=COMPONENT_ID),
                ),
                await read_optimization_policy(
                    client,
                    ObjectIdQuery(object_id=POLICY_ID),
                ),
                await read_script_definition(
                    client,
                    ObjectIdQuery(object_id=SCRIPT_ID),
                ),
                await read_form(client, FormReadQuery(form_id=FORM_ID)),
            )

    component, policy, script, form = asyncio.run(invoke())

    assert component.component_family == "integration"
    assert [item.path for item in component.files] == ["scripts/client.py"]
    assert policy.definition["severity"] == "HIGH"
    assert script.language == "python"
    assert "return True" in script.content
    assert form.form_schema["type"] == "object"
    assert form.design_mode == "schema"
