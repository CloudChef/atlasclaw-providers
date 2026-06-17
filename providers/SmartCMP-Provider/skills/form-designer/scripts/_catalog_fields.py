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
    field_type: str = "string"
    widget_id: str = "string"
    table_columns: tuple[tuple[str, str], ...] = ()


_CATALOG_FIELD_DEFINITIONS: tuple[CatalogFieldDefinition, ...] = (
    CatalogFieldDefinition(
        canonical_key="businessGroup",
        default_field_key="businessGroup",
        title_zh="业务组",
        title_en="Business Group",
        description="SmartCMP service-catalog business group field.",
        aliases=("business group", "businessGroup", "业务组"),
    ),
    CatalogFieldDefinition(
        canonical_key="businessGroup.id",
        default_field_key="businessGroup",
        title_zh="业务组 ID",
        title_en="Business Group ID",
        description="SmartCMP service-catalog business group identifier.",
        aliases=("business group id", "businessGroupId", "业务组id", "业务组 id"),
    ),
    CatalogFieldDefinition(
        canonical_key="businessGroup.name",
        default_field_key="businessGroup",
        title_zh="业务组名称",
        title_en="Business Group Name",
        description="SmartCMP service-catalog business group display name.",
        aliases=(
            "business group name",
            "businessGroupName",
            "业务组name",
            "业务组 name",
            "业务组名称",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="businessGroup.code",
        default_field_key="businessGroup",
        title_zh="业务组 Code",
        title_en="Business Group Code",
        description="SmartCMP service-catalog business group code.",
        aliases=(
            "business group code",
            "businessGroupCode",
            "业务组code",
            "业务组 code",
            "业务组编码",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="projects",
        default_field_key="projects",
        title_zh="应用",
        title_en="Application",
        description="SmartCMP service-catalog application/projects field.",
        aliases=("application", "app", "project", "projects", "应用"),
    ),
    CatalogFieldDefinition(
        canonical_key="application.id",
        default_field_key="projects",
        title_zh="应用 ID",
        title_en="Application ID",
        description="SmartCMP service-catalog application identifier.",
        aliases=(
            "app id",
            "application id",
            "projects.id",
            "project id",
            "应用id",
            "应用 id",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="application.name",
        default_field_key="projects",
        title_zh="应用名称",
        title_en="Application Name",
        description="SmartCMP service-catalog application display name.",
        aliases=(
            "app name",
            "application name",
            "projects.name",
            "project name",
            "应用name",
            "应用 name",
            "应用名称",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="application.code",
        default_field_key="projects",
        title_zh="应用 Code",
        title_en="Application Code",
        description="SmartCMP service-catalog application code.",
        aliases=(
            "app code",
            "application code",
            "projects.code",
            "project code",
            "应用code",
            "应用 code",
            "应用编码",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="owners",
        default_field_key="owners",
        title_zh="负责人",
        title_en="Owners",
        description="SmartCMP service-catalog owner list.",
        aliases=("owner list", "owners", "负责人列表"),
        field_type="array",
        widget_id="table-head",
        table_columns=(
            ("id", "ID"),
            ("name", "Name"),
            ("userName", "User Name"),
            ("userLoginId", "Login ID"),
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="owners.id",
        default_field_key="owners",
        title_zh="负责人 ID",
        title_en="Owner ID",
        description="SmartCMP service-catalog owner identifier.",
        aliases=("owner id", "owners.id", "负责人id", "负责人 id"),
    ),
    CatalogFieldDefinition(
        canonical_key="owners.name",
        default_field_key="owners",
        title_zh="负责人名称",
        title_en="Owner Name",
        description="SmartCMP service-catalog owner display name.",
        aliases=("owner name", "owners.name", "负责人name", "负责人 name", "负责人名称"),
    ),
    CatalogFieldDefinition(
        canonical_key="owners.userName",
        default_field_key="owners",
        title_zh="负责人用户名",
        title_en="Owner User Name",
        description="SmartCMP service-catalog owner user name.",
        aliases=(
            "owner username",
            "owner user name",
            "owners.userName",
            "用户名",
            "负责人用户名",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="owners.userLoginId",
        default_field_key="owners",
        title_zh="负责人登录 ID",
        title_en="Owner Login ID",
        description="SmartCMP service-catalog owner login identifier.",
        aliases=(
            "owner login id",
            "owner login",
            "owners.userLoginId",
            "userLoginId",
            "负责人登录id",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="name",
        default_field_key="name",
        title_zh="服务名称",
        title_en="Service Name",
        description="SmartCMP service-catalog request name field.",
        aliases=(
            "catalog name",
            "service catalog name",
            "standard field name",
            "标准字段 name",
        ),
    ),
    CatalogFieldDefinition(
        canonical_key="description",
        default_field_key="description",
        title_zh="服务描述",
        title_en="Service Description",
        description="SmartCMP service-catalog request description field.",
        aliases=(
            "catalog description",
            "service catalog description",
            "standard field description",
            "标准字段 description",
        ),
        widget_id="textarea",
    ),
    CatalogFieldDefinition(
        canonical_key="number",
        default_field_key="number",
        title_zh="数量",
        title_en="Number",
        description="SmartCMP service-catalog number/count field.",
        aliases=("catalog number", "number", "count", "quantity", "数量", "申请数量"),
        field_type="number",
        widget_id="number",
    ),
    CatalogFieldDefinition(
        canonical_key="executeTime",
        default_field_key="executeTime",
        title_zh="执行时间",
        title_en="Execution Time",
        description="SmartCMP service-catalog execution time.",
        aliases=("execute time", "execution time", "executeTime", "执行时间"),
    ),
    CatalogFieldDefinition(
        canonical_key="attachments",
        default_field_key="attachments",
        title_zh="附件",
        title_en="Attachments",
        description="SmartCMP service-catalog attachment list.",
        aliases=("attachment", "attachments", "附件"),
        field_type="array",
        widget_id="table-head",
        table_columns=(("name", "Name"), ("url", "URL")),
    ),
    CatalogFieldDefinition(
        canonical_key="keyValueTag",
        default_field_key="keyValueTag",
        title_zh="键值标签",
        title_en="Key-Value Tags",
        description="SmartCMP service-catalog key-value tag list.",
        aliases=(
            "key value tag",
            "key value tags",
            "key-value tag",
            "key-value tags",
            "键值标签",
        ),
        field_type="array",
        widget_id="table-head",
        table_columns=(("key", "Key"), ("value", "Value")),
    ),
    CatalogFieldDefinition(
        canonical_key="cloudResourceTag",
        default_field_key="cloudResourceTag",
        title_zh="云资源标签",
        title_en="Cloud Resource Tags",
        description="SmartCMP service-catalog cloud resource tag list.",
        aliases=(
            "cloud resource tag",
            "cloud resource tags",
            "resource tag",
            "resource tags",
            "云资源标签",
            "资源标签",
        ),
        field_type="array",
        widget_id="table-head",
        table_columns=(("key", "Key"), ("value", "Value")),
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
            `businessGroup.code`.
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
                if alias == definition.default_field_key:
                    # Several semantic subfields, such as `businessGroup.code`
                    # and `businessGroup.name`, share one SmartCMP UI field key.
                    # Keep the first exact-key mapping and let explicit aliases
                    # such as "业务组 code" resolve to the semantic subfield.
                    continue
                raise ValueError(
                    "Catalog field alias collision for "
                    f"{alias!r}: {existing.canonical_key} and {definition.canonical_key}"
                )
            aliases[normalized_alias] = definition
    return aliases


_ALIAS_INDEX = _register_aliases()
