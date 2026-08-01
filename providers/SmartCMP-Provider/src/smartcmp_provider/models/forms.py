"""Typed contracts for shared SmartCMP form reads and design."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FormReadQuery(BaseModel):
    """Select one form by ID or a Provider-validated SmartCMP editor URL."""

    model_config = ConfigDict(frozen=True)

    form_id: str = ""
    form_url: str = ""

    @model_validator(mode="after")
    def validate_source(self) -> FormReadQuery:
        """Require an ID or URL while allowing Provider-level cross-checking."""

        if not self.form_id.strip() and not self.form_url.strip():
            raise ValueError("form_id or form_url is required.")
        return self


class FormReadResult(BaseModel):
    """Return one parsed SmartCMP form definition."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    form_id: str
    name: str
    description: str
    form_schema: dict[str, Any] = Field(
        validation_alias="schema",
        serialization_alias="schema",
    )
    model: dict[str, Any]
    design_mode: str
    component_count: int
    source_route: str
    raw_content_keys: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class FormDesignInput(BaseModel):
    """Describe a read-only SmartCMP form schema design operation."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    mode: Literal["new", "modify", "regenerate"]
    schema_json_value: str = Field(
        default="",
        validation_alias="schema_json",
        serialization_alias="schema_json",
    )
    form_id: str = ""
    form_url: str = ""
    change_summary: str = ""
    catalog_fields_json: str = ""
    value_expressions_json: str = ""
    requested_fields_json: str = ""


class FormDesignResult(BaseModel):
    """Return a complete replacement schema without writing SmartCMP."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    mode: str
    source: dict[str, Any]
    warnings: tuple[str, ...]
    changeSummary: str
    form_schema: dict[str, Any] = Field(
        validation_alias="schema",
        serialization_alias="schema",
    )
