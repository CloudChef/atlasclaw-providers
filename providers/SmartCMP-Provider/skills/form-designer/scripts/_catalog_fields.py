#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Build on-demand SmartCMP service-catalog standard field schemas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CatalogFieldDefinition:
    """Metadata for a SmartCMP service-catalog standard context field.

    Standard catalog fields are not injected into every generated form. Callers
    use these definitions only when the user or LLM explicitly asks for a
    built-in catalog context field to appear in the form schema.

    `field_type`, `widget_id`, and `table_columns` describe only the generated
    display field. They do not imply that SmartCMP catalog source objects are
    written back or that the request workflow is involved.
    """

    canonical_key: str
    default_field_key: str
    title_zh: str
    title_en: str
    description: str
    aliases: tuple[str, ...]
    value_read_paths: tuple[str, ...]
    field_type: str = "string"
    widget_id: str = "string"
    table_columns: tuple[tuple[str, str], ...] = ()


_CATALOG_FIELD_DEFINITIONS: tuple[CatalogFieldDefinition, ...] = (
    CatalogFieldDefinition(
        canonical_key="businessGroup",
        default_field_key="businessGroup",
        title_zh="业务组",
        title_en="Business Group",
        description="SmartCMP service-catalog business group UI field.",
        aliases=("business group", "businessGroup", "businessGroupName", "BusinessGroup", "业务组"),
        value_read_paths=(
            "catalogServiceRequest.exts.businessGroup.name",
            "catalogServiceRequest.exts.businessGroupName",
            "catalogServiceRequest.exts.businessGroup",
            "businessGroupName",
            "businessGroup",
            "BusinessGroup",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="projects",
        default_field_key="projects",
        title_zh="应用系统",
        title_en="Application",
        description="SmartCMP service-catalog application UI field.",
        aliases=("application", "app", "project", "projects", "Projects", "应用", "应用系统"),
        value_read_paths=(
            "catalogServiceRequest.exts.project.name",
            "catalogServiceRequest.exts.project",
            "projects",
            "Projects",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="owners",
        default_field_key="owners",
        title_zh="所有者",
        title_en="Owners",
        description="SmartCMP service-catalog owner UI field.",
        aliases=("owner", "owners", "Owners", "所有者"),
        value_read_paths=(
            "catalogServiceRequest.exts.owner.name",
            "catalogServiceRequest.exts.owner",
            "owners",
            "Owners",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="name",
        default_field_key="name",
        title_zh="名称",
        title_en="Name",
        description="SmartCMP service-catalog name UI field.",
        aliases=("catalog name", "service catalog name", "Name", "名称"),
        value_read_paths=("name", "Name"),
    ),
)

_CATALOG_FIELDS_BY_KEY: dict[str, CatalogFieldDefinition] = {
    definition.canonical_key: definition for definition in _CATALOG_FIELD_DEFINITIONS
}
_ALIAS_INDEX: dict[str, CatalogFieldDefinition] = {}


def iter_catalog_field_definitions() -> tuple[CatalogFieldDefinition, ...]:
    """Return all supported service-catalog standard field definitions."""
    return _CATALOG_FIELD_DEFINITIONS


def resolve_catalog_field_alias(value: str) -> CatalogFieldDefinition | None:
    """Resolve a human or schema alias to a catalog field definition.

    Matching accepts canonical keys, default field keys, and curated aliases.
    Cosmetic separators such as spaces, underscores, hyphens, colon variants,
    slashes, and case differences are ignored to support natural LLM/user input.

    Args:
        value: Candidate field name, title, or alias.

    Returns:
        The matching catalog field definition, or `None` when the value is not
        a known catalog field.
    """
    if not isinstance(value, str):
        return None
    return _ALIAS_INDEX.get(_normalize_alias(value))


def build_catalog_field_schema(
    canonical_key: str,
    *,
    field_key: str | None = None,
    language: str = "zh",
    hidden: bool = False,
) -> dict[str, Any]:
    """Build a read-only SmartCMP schema field for a catalog standard field.

    Args:
        canonical_key: Stable SmartCMP catalog field key such as
            `businessGroup`.
        field_key: Optional schema property key/id. The definition default is
            used when omitted.
        language: Title language. `zh` uses the Chinese title; all other values
            use the English title.
        hidden: Whether to build the schema as a hidden technical field.

    Returns:
        A SmartCMP schema field object with visibility enabled and modification
        disabled in both request and approval phases.

    Raises:
        ValueError: If `canonical_key` is not supported.
    """
    definition = _CATALOG_FIELDS_BY_KEY.get(canonical_key)
    if definition is None:
        raise ValueError(f"Unknown SmartCMP catalog field: {canonical_key}")

    schema_key = field_key or definition.default_field_key
    if definition.table_columns:
        field = _build_table_schema(definition, schema_key, language)
    else:
        field = _build_scalar_schema(definition, schema_key, language)

    if hidden:
        field["hidden"] = True
        field["widget"]["id"] = "hidden"

    return field


def _build_scalar_schema(
    definition: CatalogFieldDefinition,
    field_key: str,
    language: str,
) -> dict[str, Any]:
    return {
        "id": field_key,
        "title": _title_for_language(definition, language),
        "description": definition.description,
        "type": definition.field_type,
        "widget": {"id": definition.widget_id},
        "config": _read_only_config(),
        "x-smartcmp": _builtin_metadata(definition),
    }


def _build_table_schema(
    definition: CatalogFieldDefinition,
    field_key: str,
    language: str,
) -> dict[str, Any]:
    item_properties = {
        column_key: {
            "id": column_key,
            "title": column_title,
            "type": "string",
            "widget": {"id": "string"},
        }
        for column_key, column_title in definition.table_columns
    }
    return {
        "id": field_key,
        "title": _title_for_language(definition, language),
        "description": definition.description,
        "type": definition.field_type,
        "widget": {"id": definition.widget_id},
        "items": {
            "type": "object",
            "widget": {"id": "table-body"},
            "properties": item_properties,
            "fieldsets": [
                {
                    "id": f"{field_key}-fieldset-default",
                    "title": _title_for_language(definition, language),
                    "description": "",
                    "name": "",
                    "fields": list(item_properties.keys()),
                }
            ],
        },
        "config": _read_only_config(),
        "x-smartcmp": _builtin_metadata(definition),
    }


def _builtin_metadata(definition: CatalogFieldDefinition) -> dict[str, str]:
    """Record both semantic catalog path and exact SmartCMP UI field key."""
    return {
        "builtinCatalogField": definition.canonical_key,
        "uiFieldKey": definition.default_field_key,
    }


def _read_only_config() -> dict[str, dict[str, bool]]:
    return {
        "visibility": {
            "allowInRequest": True,
            "allowInApproval": True,
        },
        "modification": {
            "allowInRequest": False,
            "allowInApproval": False,
        },
    }


def _title_for_language(definition: CatalogFieldDefinition, language: str) -> str:
    return definition.title_zh if language.lower().startswith("zh") else definition.title_en


def _normalize_alias(value: str) -> str:
    return re.sub(r"[\s_\-:：/]+", "", value).casefold()


def _register_aliases() -> dict[str, CatalogFieldDefinition]:
    aliases: dict[str, CatalogFieldDefinition] = {}
    for definition in _CATALOG_FIELD_DEFINITIONS:
        for alias in (
            definition.canonical_key,
            definition.default_field_key,
            definition.title_zh,
            definition.title_en,
            *definition.aliases,
        ):
            normalized_alias = _normalize_alias(alias)
            existing = aliases.get(normalized_alias)
            if existing is not None and existing.canonical_key != definition.canonical_key:
                raise ValueError(
                    "Catalog field alias collision for "
                    f"{alias!r}: {existing.canonical_key} and {definition.canonical_key}"
                )
            aliases[normalized_alias] = definition
    return aliases


_ALIAS_INDEX = _register_aliases()
