# User-Language Wording for SmartCMP Provider Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Shift SmartCMP provider discovery wording from product-name-first language to user-language-first wording while preserving internal identifiers and technical sections.

**Architecture:** Keep `provider_type`, `display_name`, auth/config fields, and tool registration tied to SmartCMP/CMP. Rewrite `description`, `capabilities`, `use_when`, `triggers`, and nearby explanatory text so they match what users actually say, such as requesting VMs, checking approvals, or viewing alarms.

**Tech Stack:** Markdown metadata in `PROVIDER.md` and `SKILL.md`, plus lightweight pytest layout checks.

---

### Task 1: Update Provider Discovery Wording

**Files:**
- Modify: `providers/SmartCMP-Provider/PROVIDER.md`

**Step 1: Rewrite top-level discovery metadata**

Update `capabilities` and `use_when` so they describe user intents such as requesting resources, checking alarms, and handling approvals without assuming the user knows the SmartCMP product name.

**Step 2: Rewrite nearby skill summary text**

Adjust the summary paragraph and the `Provided Skills` / `Core Skills` descriptions so they stay understandable in user language while leaving technical configuration and API notes intact.

**Step 3: Review for scope**

Confirm the file still keeps SmartCMP in internal identity and technical sections only.

### Task 2: Update Skill Trigger Wording

**Files:**
- Modify: `providers/SmartCMP-Provider/skills/datasource/SKILL.md`
- Modify: `providers/SmartCMP-Provider/skills/request/SKILL.md`
- Modify: `providers/SmartCMP-Provider/skills/approval/SKILL.md`
- Modify: `providers/SmartCMP-Provider/skills/alarm/SKILL.md`
- Modify: `providers/SmartCMP-Provider/skills/cost-optimization/SKILL.md`
- Modify: `providers/SmartCMP-Provider/skills/request-decomposition-agent/SKILL.md`
- Modify: `providers/SmartCMP-Provider/skills/preapproval-agent/SKILL.md`
- Modify: `providers/SmartCMP-Provider/test/test_cost_optimization_layout.py`

**Step 1: Rewrite frontmatter discovery text**

Update `description`, `use_when`, and similar trigger-facing lines to use user language such as "request a VM", "check pending approvals", and "view alarms".

**Step 2: Rewrite nearby purpose text**

Update the heading/introduction/purpose text near the top of each skill so the first explanation a reader sees also matches user language.

**Step 3: Align the layout test**

Update the cost optimization layout test so it validates the new description prefix instead of the old SmartCMP-first wording.

**Step 4: Verify**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_cost_optimization_layout.py providers/SmartCMP-Provider/test/test_alarm_layout.py -q
```

Expected: passing tests with no failures.
