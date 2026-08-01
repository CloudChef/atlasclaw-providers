"""Critical form-design contracts owned by SmartCMP Provider."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from smartcmp_provider.auth.resolver import resolve_provided_request
from smartcmp_provider.forms.catalog_insertions import apply_catalog_fields
from smartcmp_provider.forms.definitions import parse_form_edit_url
from smartcmp_provider.forms.design import prepare_design
from smartcmp_provider.models.forms import FormDesignInput, FormReadQuery
from smartcmp_provider.forms.requested_fields import (
    constrain_schema_to_requested_fields,
)
from smartcmp_provider.services.forms import design_form, read_form
from smartcmp_provider.transport.client import SmartCmpClient


FORM_ID = "123e4567-e89b-12d3-a456-426614174000"


def test_form_url_is_bound_to_the_selected_cmp_origin() -> None:
    """Accept supported routes and reject a different SmartCMP origin."""

    source = parse_form_edit_url(
        f"https://cmp.example.com/#/main/service-model/forms/edit/{FORM_ID}",
        "https://cmp.example.com/platform-api",
    )
    assert source.form_id == FORM_ID
    assert source.route == "edit"

    with pytest.raises(ValueError, match="selected SmartCMP provider instance"):
        parse_form_edit_url(
            f"https://other.example.com/#/main/service-model/forms/edit/{FORM_ID}",
            "https://cmp.example.com/platform-api",
        )


def test_form_design_returns_a_complete_unsaved_replacement() -> None:
    """Normalize a complete schema without performing a SmartCMP write."""

    result = prepare_design(
        mode="new",
        schema_json=json.dumps(
            {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "widget": {"id": "string"},
                    }
                },
                "fieldsets": [{"fields": ["name"]}],
            }
        ),
        form_url="",
        change_summary="Add a request name.",
        catalog_fields_json="",
        value_expressions_json="",
        requested_fields_json=json.dumps(["name"]),
        base_url="https://cmp.example.com/platform-api",
        source_form=None,
    )

    assert result["changeSummary"] == "Add a request name."
    assert result["schema"]["properties"]["name"]["type"] == "string"
    assert "schemaFormValid" in result["schema"]["properties"]


def test_form_design_rejects_unsafe_placeholder_javascript() -> None:
    """Do not return abbreviated JavaScript that can submit invalid values."""

    schema = {
        "type": "object",
        "properties": {
            "computed": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "expression": (
                            "function(model, sourceParams, schema, unused, cfg) "
                            "{ ... }"
                        )
                    }
                },
            }
        },
        "fieldsets": [{"fields": ["computed"]}],
    }
    with pytest.raises(ValueError, match="abbreviated JavaScript"):
        prepare_design(
            mode="new",
            schema_json=json.dumps(schema),
            form_url="",
            change_summary="",
            catalog_fields_json="",
            value_expressions_json="",
            requested_fields_json=json.dumps(["computed"]),
            base_url="https://cmp.example.com/platform-api",
            source_form=None,
        )


def test_url_form_source_is_preserved_through_provider_validation() -> None:
    """Preserve editor route and URL-specific JavaScript validation in Provider."""

    schema = {
        "type": "object",
        "properties": {
            "computed": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "expression": "function(model) { return model.computed; }",
                    }
                },
            }
        },
        "fieldsets": [{"fields": ["computed"]}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": FORM_ID,
                "name": "Legacy form",
                "content": {
                    "schema": {"type": "object", "properties": {}},
                    "model": {},
                    "designMode": "schema",
                },
            },
            request=request,
        )

    request = resolve_provided_request(
        instance_name="cmp-test",
        base_url="https://cmp.example.com",
        subject="user-1",
        auth_type="cookie",
        credential_value="session-secret",
        trace_id="form-url-design",
    )

    async def invoke() -> None:
        async with SmartCmpClient(
            request,
            transport=httpx.MockTransport(handler),
        ) as client:
            form = await read_form(
                client,
                FormReadQuery(
                    form_url=(
                        "https://cmp.example.com/#/main/service-model/forms/"
                        f"design/{FORM_ID}"
                    )
                ),
            )
            assert form.source_route == "design"
            await design_form(
                client,
                FormDesignInput(
                    mode="modify",
                    schema_json=json.dumps(schema),
                    form_id=FORM_ID,
                    form_url=(
                        "https://cmp.example.com/#/main/service-model/forms/"
                        f"edit/{FORM_ID}"
                    ),
                ),
            )

    with pytest.raises(ValueError, match="URL-based form changes"):
        asyncio.run(invoke())


def test_catalog_insertion_and_requested_fields_remain_provider_operations() -> None:
    """Keep reusable catalog and field-selection rules out of Skill scripts."""

    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "widget": {"id": "string"}},
            "unused": {"type": "string", "widget": {"id": "string"}},
        },
        "fieldsets": [{"fields": ["name", "unused"]}],
    }
    warnings = apply_catalog_fields(
        schema,
        json.dumps(
            [
                {
                    "field": "businessGroup",
                }
            ]
        ),
    )
    warnings.extend(
        constrain_schema_to_requested_fields(
            schema,
            ["name", "businessGroup"],
            require_all=True,
        )
    )

    assert "businessGroup" in schema["properties"]
    assert "unused" not in schema["properties"]
    assert isinstance(warnings, list)
