# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Verify confirmation metadata without changing SmartCMP domain tool contracts."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROVIDER_ROOT / "skills"

MUTATION_TOOLS = {
    ("alarm", "operate"): "smartcmp_operate_alert",
    ("approval", "approve"): "smartcmp_approve",
    ("approval", "reject"): "smartcmp_reject",
    ("cost-optimization", "execute"): "smartcmp_execute_cost_optimization",
    ("request", "submit"): "smartcmp_submit_request",
    ("resource", "power"): "smartcmp_operate_resource",
}

# These hashes pin the pre-existing public argument schemas. Adding confirmation
# metadata must not rewrite a domain Tool's inputs or CLI contract.
PARAMETER_SCHEMA_SHA256 = {
    ("alarm", "operate"): "0bb38b3d245c8f30deabe6465bd74891cd8f63c7ee28a6137277a5187e41a6f3",
    ("approval", "approve"): "1e952c472a68190546027d78d1a11f5ab4c6e8111960fe02e5e2e3d2c2447135",
    ("approval", "reject"): "31b311d92c0f7abd3b522a65cda4d0849e021d962ff9f8d3351404cbb7d92b04",
    ("request", "submit"): "039c13f870b059bc81d252fbcaaea7e0bd4e46bab3dd02404b87b291d3b6dd1c",
    ("resource", "power"): "8ada8909cd26fb6e0d000a1c1cd3af542e0dc5a98a9148825c954482577fd7d6",
}


def _frontmatter(skill: str) -> str:
    """Return one Skill's YAML frontmatter as text."""
    text = (SKILLS_ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
    return text.split("---", 2)[1]


def _literal_block(frontmatter: str, field: str) -> str | None:
    """Return an indented YAML literal block without interpreting its schema."""
    match = re.search(rf"^{re.escape(field)}: \|\n((?:  .*\n)+)", frontmatter, re.MULTILINE)
    return match.group(1) if match else None


def test_user_facing_mutation_tools_require_server_confirmation() -> None:
    """Only interactive SmartCMP mutations should declare the generic confirmation policy."""
    discovered: dict[tuple[str, str], str] = {}

    for skill_path in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        skill = skill_path.parent.name
        frontmatter = _frontmatter(skill)
        for match in re.finditer(r"^tool_([a-z0-9_]+)_requires_approval: true$", frontmatter, re.MULTILINE):
            prefix = match.group(1)
            name_match = re.search(rf'^tool_{re.escape(prefix)}_name: "([^"]+)"$', frontmatter, re.MULTILINE)
            assert name_match is not None
            assert re.search(rf'^tool_{re.escape(prefix)}_effect: "mutate"$', frontmatter, re.MULTILINE)
            discovered[(skill, prefix)] = name_match.group(1)

    assert discovered == MUTATION_TOOLS
    assert "requires_approval" not in _frontmatter("preapproval-agent")


def test_confirmation_metadata_preserves_domain_tool_schemas() -> None:
    """The confirmation policy must remain metadata-only for existing domain Tools."""
    for (skill, prefix), expected_hash in PARAMETER_SCHEMA_SHA256.items():
        parameters = _literal_block(_frontmatter(skill), f"tool_{prefix}_parameters")
        assert parameters is not None
        assert hashlib.sha256(parameters.encode("utf-8")).hexdigest() == expected_hash

    assert _literal_block(
        _frontmatter("cost-optimization"),
        "tool_execute_parameters",
    ) is None
