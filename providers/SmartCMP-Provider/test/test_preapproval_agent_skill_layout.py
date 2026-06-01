# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
PREAPPROVAL_SKILL = PROVIDER_ROOT / "skills" / "preapproval-agent" / "SKILL.md"


def test_preapproval_agent_requires_existing_pending_request_context() -> None:
    skill_text = PREAPPROVAL_SKILL.read_text(encoding="utf-8")

    assert "Existing pending approval request is available" in skill_text
    assert "Valid user-facing request_id is already known" in skill_text
    assert "does not create service catalog requests" in skill_text
    assert "If `request_id` is missing" in skill_text


def test_preapproval_agent_excludes_new_request_and_ticket_creation() -> None:
    skill_text = PREAPPROVAL_SKILL.read_text(encoding="utf-8")

    assert "User wants to create or submit a new service catalog request" in skill_text
    assert "User wants to create a ticket or work order" in skill_text
    assert "even if the requested catalog name contains approval or pre-approval wording" in skill_text
    assert "use request skill" in skill_text
