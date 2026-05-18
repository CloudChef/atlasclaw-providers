"""Configuration loading for the Markdown Vault provider runtime."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any


PROVIDER_TYPE = "markdown-vault"
DEFAULT_INSTANCE_NAME = "default"
DEFAULT_INCLUDE_GLOBS = ["**/*.md"]
DEFAULT_EXCLUDE_GLOBS = [".obsidian/**", ".git/**", "**/.*/**", "**/node_modules/**"]
DEFAULT_TABLE_PREFIX = "markdown_vault_"


@dataclass(frozen=True)
class MarkdownVaultConfig:
    """Validated runtime configuration for one Markdown vault provider instance."""

    instance_name: str
    instance_id: str
    vault_path: Path
    index_backend: str
    index_path: Path | None
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str
    mysql_charset: str
    mysql_tls: bool
    table_prefix: str
    include_globs: list[str]
    exclude_globs: list[str]
    max_file_bytes: int
    max_chunk_chars: int


class MarkdownVaultConfigError(ValueError):
    """Raised when a Markdown vault provider instance is missing required configuration."""


def load_provider_config_from_env(provider_type: str = PROVIDER_TYPE) -> MarkdownVaultConfig:
    """Load the selected provider instance from AtlasClaw runtime environment variables."""

    payload = _load_json_mapping(os.getenv("ATLASCLAW_PROVIDER_CONFIG", ""), "ATLASCLAW_PROVIDER_CONFIG")
    selected_provider = os.getenv("ATLASCLAW_PROVIDER_TYPE", "").strip() or provider_type
    selected_instance = os.getenv("ATLASCLAW_PROVIDER_INSTANCE", "").strip()
    raw_config: dict[str, Any] = {}
    instance_name = selected_instance or DEFAULT_INSTANCE_NAME
    if payload:
        try:
            raw_config, instance_name = _select_instance_config(
                payload=payload,
                provider_type=selected_provider,
                instance_name=selected_instance,
            )
        except MarkdownVaultConfigError:
            raw_config = _config_from_flat_environment()
            if not raw_config:
                raise
    if not raw_config:
        raw_config = _config_from_flat_environment()
        instance_name = selected_instance or DEFAULT_INSTANCE_NAME
    return build_markdown_vault_config(
        raw_config=raw_config,
        instance_name=instance_name,
        base_dir=Path.cwd(),
        provider_type=selected_provider,
    )


def load_provider_config_from_file(
    config_path: Path,
    instance_name: str | None = None,
    provider_type: str = PROVIDER_TYPE,
) -> MarkdownVaultConfig:
    """Load one provider instance from an AtlasClaw JSON config file for offline admin scripts."""

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MarkdownVaultConfigError(f"Config file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise MarkdownVaultConfigError(f"Config file is not valid JSON: {config_path}") from exc

    raw_config, resolved_instance = _select_instance_config(
        payload=payload,
        provider_type=provider_type,
        instance_name=(instance_name or "").strip(),
    )
    return build_markdown_vault_config(
        raw_config=raw_config,
        instance_name=resolved_instance,
        base_dir=config_path.resolve().parent,
        provider_type=provider_type,
    )


def build_markdown_vault_config(
    *,
    raw_config: dict[str, Any],
    instance_name: str,
    base_dir: Path,
    provider_type: str = PROVIDER_TYPE,
) -> MarkdownVaultConfig:
    """Normalize and validate one Markdown vault provider instance config."""

    if not isinstance(raw_config, dict):
        raise MarkdownVaultConfigError("Provider instance config must be an object.")

    vault_path = _required_path(raw_config, "vault_path", base_dir=base_dir)
    if not vault_path.is_dir():
        raise MarkdownVaultConfigError(f"vault_path must be an existing directory: {vault_path}")

    index_backend = str(raw_config.get("index_backend") or "sqlite").strip().lower()
    if index_backend not in {"sqlite", "mysql"}:
        raise MarkdownVaultConfigError("index_backend must be either 'sqlite' or 'mysql'.")

    index_path = _optional_path(raw_config, "index_path", base_dir=base_dir)
    if index_backend == "sqlite" and index_path is None:
        raise MarkdownVaultConfigError("index_path is required when index_backend is 'sqlite'.")

    mysql_host = str(raw_config.get("mysql_host") or "").strip()
    mysql_port = _int_value(raw_config.get("mysql_port"), default=3306, name="mysql_port")
    mysql_database = str(raw_config.get("mysql_database") or "").strip()
    mysql_user = str(raw_config.get("mysql_user") or "").strip()
    mysql_password = str(raw_config.get("mysql_password") or "").strip()
    mysql_charset = str(raw_config.get("mysql_charset") or "utf8mb4").strip() or "utf8mb4"
    mysql_tls = _bool_value(raw_config.get("mysql_tls"), default=False)
    table_prefix = str(raw_config.get("mysql_table_prefix") or DEFAULT_TABLE_PREFIX).strip()
    _validate_table_prefix(table_prefix)

    if index_backend == "mysql":
        missing = [
            name
            for name, value in {
                "mysql_host": mysql_host,
                "mysql_database": mysql_database,
                "mysql_user": mysql_user,
                "mysql_password": mysql_password,
            }.items()
            if not value
        ]
        if missing:
            raise MarkdownVaultConfigError(
                f"MySQL index backend requires fields: {', '.join(missing)}."
            )

    max_file_bytes = _int_value(raw_config.get("max_file_bytes"), default=1048576, name="max_file_bytes")
    max_chunk_chars = _int_value(raw_config.get("max_chunk_chars"), default=1800, name="max_chunk_chars")
    if max_file_bytes <= 0:
        raise MarkdownVaultConfigError("max_file_bytes must be greater than zero.")
    if max_chunk_chars < 200:
        raise MarkdownVaultConfigError("max_chunk_chars must be at least 200.")

    normalized_instance = instance_name.strip() or DEFAULT_INSTANCE_NAME
    return MarkdownVaultConfig(
        instance_name=normalized_instance,
        instance_id=f"{provider_type}:{normalized_instance}",
        vault_path=vault_path,
        index_backend=index_backend,
        index_path=index_path,
        mysql_host=mysql_host,
        mysql_port=mysql_port,
        mysql_database=mysql_database,
        mysql_user=mysql_user,
        mysql_password=mysql_password,
        mysql_charset=mysql_charset,
        mysql_tls=mysql_tls,
        table_prefix=table_prefix,
        include_globs=_string_list(raw_config.get("include_globs"), DEFAULT_INCLUDE_GLOBS),
        exclude_globs=_string_list(raw_config.get("exclude_globs"), DEFAULT_EXCLUDE_GLOBS),
        max_file_bytes=max_file_bytes,
        max_chunk_chars=max_chunk_chars,
    )


def _select_instance_config(
    *,
    payload: dict[str, Any],
    provider_type: str,
    instance_name: str,
) -> tuple[dict[str, Any], str]:
    """Find a provider instance config across supported AtlasClaw config shapes."""

    candidates: list[Any] = []
    for key in ("provider_config", "provider_instances", "service_providers", "providers"):
        if isinstance(payload.get(key), dict):
            candidates.append(payload[key])
    candidates.append(payload)

    for candidate in candidates:
        raw = _extract_provider_payload(candidate, provider_type)
        if raw is None:
            continue
        selected, resolved_name = _extract_instance(raw, instance_name)
        if selected is not None:
            return selected, resolved_name

    raise MarkdownVaultConfigError(
        f"Provider config for {provider_type!r}"
        + (f" instance {instance_name!r}" if instance_name else "")
        + " was not found."
    )


def _extract_provider_payload(candidate: Any, provider_type: str) -> Any | None:
    if not isinstance(candidate, dict):
        return None
    if provider_type in candidate:
        return candidate[provider_type]
    normalized = provider_type.replace("-", "_")
    if normalized in candidate:
        return candidate[normalized]
    return candidate if _looks_like_instance_config(candidate) else None


def _extract_instance(raw: Any, instance_name: str) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(raw, dict):
        return None, instance_name or DEFAULT_INSTANCE_NAME
    if _looks_like_instance_config(raw):
        return raw, instance_name or str(raw.get("name") or DEFAULT_INSTANCE_NAME)
    if instance_name:
        selected = raw.get(instance_name)
        if isinstance(selected, dict):
            return selected, instance_name
        raise MarkdownVaultConfigError(f"Provider instance not found: {instance_name}")
    for name, value in raw.items():
        if isinstance(value, dict) and _looks_like_instance_config(value):
            return value, str(name)
    return None, instance_name or DEFAULT_INSTANCE_NAME


def _looks_like_instance_config(value: dict[str, Any]) -> bool:
    return "vault_path" in value or "index_backend" in value or "index_path" in value


def _config_from_flat_environment() -> dict[str, Any]:
    config: dict[str, Any] = {}
    for name in (
        "vault_path",
        "index_backend",
        "index_path",
        "mysql_host",
        "mysql_port",
        "mysql_database",
        "mysql_user",
        "mysql_password",
        "mysql_charset",
        "mysql_tls",
        "mysql_table_prefix",
        "include_globs",
        "exclude_globs",
        "max_file_bytes",
        "max_chunk_chars",
    ):
        env_value = os.getenv(name.upper())
        if env_value is not None:
            config[name] = env_value
    return config


def _required_path(raw_config: dict[str, Any], name: str, *, base_dir: Path) -> Path:
    value = str(raw_config.get(name) or "").strip()
    if not value:
        raise MarkdownVaultConfigError(f"{name} is required.")
    return _resolve_path(value, base_dir=base_dir)


def _optional_path(raw_config: dict[str, Any], name: str, *, base_dir: Path) -> Path | None:
    value = str(raw_config.get(name) or "").strip()
    if not value:
        return None
    return _resolve_path(value, base_dir=base_dir)


def _resolve_path(value: str, *, base_dir: Path) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(value)))
    if not expanded.is_absolute():
        expanded = base_dir / expanded
    return expanded.resolve()


def _string_list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, list):
        items = [str(item).strip() for item in value]
    else:
        text = str(value).strip()
        items = [item.strip() for item in text.replace("\n", ",").split(",")]
    return [item for item in items if item] or list(default)


def _int_value(value: Any, *, default: int, name: str) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MarkdownVaultConfigError(f"{name} must be an integer.") from exc


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "tls"}


def _validate_table_prefix(prefix: str) -> None:
    if not re.fullmatch(r"(?:[A-Za-z_][A-Za-z0-9_]*)?", prefix):
        raise MarkdownVaultConfigError(
            "mysql_table_prefix must be empty or start with a letter or underscore "
            "and contain only letters, digits, and underscores."
        )


def _load_json_mapping(value: str, source_name: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise MarkdownVaultConfigError(f"{source_name} is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise MarkdownVaultConfigError(f"{source_name} must be a JSON object.")
    return payload
