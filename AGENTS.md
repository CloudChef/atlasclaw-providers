# AGENTS.md - AtlasClaw Providers Guidelines

## Repository Overview

This repository is organized into a few top-level modules:

- `providers/`: concrete provider packages such as `SmartCMP-Provider` and `jira`
- `skills/`: shared reusable skills, templates, and helper tooling that are not tied to a single provider
- `docs/`: repository-level architecture notes, design plans, and supporting assets
- `.agentdocs/`: optional AI-only working notes and memory files used during execution

Most provider work happens under a provider package with a layout similar to:

```text
providers/<provider-name>/
|-- PROVIDER.md
|-- README.md
|-- skills/
|   `-- <skill-name>/
|       |-- SKILL.md
|       |-- scripts/
|       |-- references/
|       `-- test/              # optional, skill-scoped tests
|-- docs/                      # optional, provider-specific plans or design notes
`-- test/                      # optional, provider-level tests
```

Directory responsibilities:

- `PROVIDER.md`: provider contract, configuration shape, and authentication model
- `README.md`: human-readable provider overview
- `skills/<skill-name>/SKILL.md`: skill metadata, usage guidance, and tool entrypoints
- `skills/<skill-name>/scripts/`: executable integration logic and helpers
- `skills/<skill-name>/references/`: API mappings, workflows, and examples kept close to the skill
- `docs/` and `test/`: provider-specific design notes and verification coverage

## Code Style

- Comments must be in English
- Prefer wide lines suitable for large screens; avoid over-wrapping
- Do not split simple logic into many tiny methods unless reuse justifies it
- Avoid breaking short code across many lines
- Keep validation pragmatic: validate external input, persistence integrity, and core trading invariants, but do not add layers of redundant defensive checks that do not improve correctness

## Code Documentation Rules

- Every public class must have a class-level docstring explaining its responsibility
- Every public method or function must have a docstring describing:
  - purpose
  - parameters
  - return value
  - possible exceptions or error cases
- Add short comments for non-obvious business rules, edge cases, and tricky logic
- Do not add trivial comments that merely restate the code
- Prefer self-explanatory naming first; comments are for intent, constraints, and reasoning

## Analyze Field Impact Before Changing Existing Fields

Before changing an existing field, including its format, storage style, or calculation logic, you must:

1. analyze all call sites, including `getXxx()` and `setXxx()` references
2. confirm the stored data format contract
3. check formulas or strategy logic that depend on that format
4. explain the impact to the user before deciding the final change

## Architecture Rule

Extract truly reusable common logic to the right shared place. Do not create local one-off abstractions that make the code harder to follow.

## Documentation and Memory

Use documentation and memory files to capture background context and align execution constraints.
All documentation and memory files must use Markdown and live under `.agentdocs/` and its subdirectories.
These files are for AI agents only and should not contain human-facing explanations.
Use `.agentdocs/index.md` as the index document to record each document's primary content, when it should be read, and any global key memories.

# Coding and Design Principles

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- Do not add redundant null checks unless there is a real logic path that needs them.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" -> "Write tests for invalid inputs, then make them pass"
- "Fix the bug" -> "Write a test that reproduces it, then make it pass"
- "Refactor X" -> "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

# Commit Messages
Use Conventional Commits: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
Format:
- `<type>(<scope>): <summary>`
Example:
- `docs(config): align webhook env var examples`
