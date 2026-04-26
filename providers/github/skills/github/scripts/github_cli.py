from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


_TOKEN_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsru]_[A-Za-z0-9_]+"),
    re.compile(r"(Authorization:\s*(?:Bearer|token)\s+)[^\s'\"]+", re.IGNORECASE),
)


def _get_extra(ctx: Any) -> dict[str, Any]:
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", {}) if deps is not None else {}
    return extra if isinstance(extra, dict) else {}


def _pick_provider_instance(extra: dict[str, Any]) -> tuple[str, dict[str, Any]] | tuple[str, None]:
    selected = extra.get("provider_instance")
    selected_type = str(extra.get("provider_type", "") or "").strip().lower()
    selected_name = str(extra.get("provider_instance_name", "") or "").strip()
    if isinstance(selected, dict) and (not selected_type or selected_type == "github"):
        return selected_name or str(selected.get("instance_name", "") or "selected"), dict(selected)

    provider_instances = extra.get("provider_instances", {})
    github_instances = {}
    if isinstance(provider_instances, dict):
        raw_instances = provider_instances.get("github", {})
        if isinstance(raw_instances, dict):
            github_instances = raw_instances

    if selected_type == "github" and selected_name and selected_name in github_instances:
        selected_config = github_instances.get(selected_name)
        if isinstance(selected_config, dict):
            return selected_name, dict(selected_config)

    if len(github_instances) == 1:
        instance_name = next(iter(github_instances.keys()))
        instance_config = github_instances.get(instance_name)
        if isinstance(instance_config, dict):
            return str(instance_name), dict(instance_config)

    if len(github_instances) > 1:
        return "", None

    return "", None


def _derive_hostname(instance: dict[str, Any]) -> str:
    hostname = str(instance.get("hostname", "") or "").strip()
    if hostname:
        return hostname

    base_url = str(instance.get("base_url", "") or "").strip()
    if not base_url:
        return "github.com"
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    host = parsed.hostname or ""
    if host == "api.github.com":
        return "github.com"
    return host or "github.com"


def _is_github_dot_com_host(hostname: str) -> bool:
    normalized = hostname.strip().lower()
    return normalized == "github.com" or normalized.endswith(".ghe.com")


def _coerce_args(args: Any) -> list[str]:
    if isinstance(args, str):
        return shlex.split(args)
    if isinstance(args, (list, tuple)):
        return [str(item) for item in args if str(item).strip()]
    return []


def _coerce_timeout(value: Any, fallback: Any = 120) -> int:
    candidate = value if value not in (None, "") else fallback
    try:
        timeout = int(candidate)
    except (TypeError, ValueError):
        timeout = 120
    return max(1, min(timeout, 300))


def _redact_text(value: Any, secrets: list[str]) -> str:
    text = str(value or "")
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}***" if match.groups() else "***", text)
    return text


def _build_env(
    *,
    base_env: dict[str, str],
    instance: dict[str, Any],
    token: str,
    repo: str,
    gh_config_dir: str,
) -> dict[str, str]:
    env = dict(base_env)
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        env.pop(key, None)

    hostname = _derive_hostname(instance)
    if _is_github_dot_com_host(hostname):
        env["GH_TOKEN"] = token
    else:
        env["GH_ENTERPRISE_TOKEN"] = token

    env["GH_HOST"] = hostname
    env["GH_PROMPT_DISABLED"] = "1"
    env["GH_CONFIG_DIR"] = gh_config_dir
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    env["GH_NO_EXTENSION_UPDATE_NOTIFIER"] = "1"
    env.setdefault("NO_COLOR", "1")
    if repo:
        env["GH_REPO"] = repo
    return env


async def github_cli_handler(
    ctx: Any,
    *,
    args: Any,
    repo: str | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Run a gh CLI command using the selected GitHub provider instance."""
    extra = _get_extra(ctx)
    instance_name, instance = _pick_provider_instance(extra)
    if instance is None:
        provider_instances = extra.get("provider_instances", {})
        github_instances = (
            provider_instances.get("github", {})
            if isinstance(provider_instances, dict)
            else {}
        )
        available = sorted(github_instances.keys()) if isinstance(github_instances, dict) else []
        if available:
            return {
                "success": False,
                "error": (
                    "GitHub provider instance is ambiguous. Select one instance before "
                    f"running github_cli. Available instances: {', '.join(available)}"
                ),
            }
        return {
            "success": False,
            "error": "GitHub provider instance is not configured for this user.",
        }

    token = str(instance.get("user_token", "") or "").strip()
    if not token:
        return {
            "success": False,
            "error": (
                "GitHub user_token is not configured. Add a GitHub personal access token "
                "in AtlasClaw Provider Tokens for this provider instance."
            ),
        }

    command_args = _coerce_args(args)
    if not command_args:
        return {"success": False, "error": "github_cli requires non-empty args."}
    if command_args[:2] == ["auth", "login"]:
        return {
            "success": False,
            "error": "gh auth login is not supported in provider runtime; configure user_token instead.",
        }

    timeout = _coerce_timeout(timeout_seconds, instance.get("timeout_seconds", 120))
    repo_value = str(repo or "").strip()
    secrets = [token]

    with tempfile.TemporaryDirectory(prefix="atlasclaw-gh-") as gh_config_dir:
        env = _build_env(
            base_env=os.environ,
            instance=instance,
            token=token,
            repo=repo_value,
            gh_config_dir=gh_config_dir,
        )
        cmd = ["gh", *command_args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
                cwd=str(Path.cwd()),
            )
        except FileNotFoundError:
            return {
                "success": False,
                "error": "GitHub CLI executable 'gh' was not found in PATH.",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"GitHub CLI command timed out after {timeout} seconds.",
                "command": ["gh", *command_args],
            }
        except Exception as exc:
            return {
                "success": False,
                "error": _redact_text(str(exc), secrets),
                "command": ["gh", *command_args],
            }

    stdout = _redact_text(result.stdout, secrets)
    stderr = _redact_text(result.stderr, secrets)
    payload: dict[str, Any] = {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "output": stdout,
        "error": stderr if result.returncode != 0 else "",
        "command": ["gh", *command_args],
        "provider": {
            "provider_type": "github",
            "instance_name": instance_name,
            "hostname": _derive_hostname(instance),
            "repo": repo_value,
        },
    }
    if result.returncode == 0 and stderr:
        payload["stderr"] = stderr
    return payload
