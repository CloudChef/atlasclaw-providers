---
name: "script-designer"
description: "Use when reading or modifying the script content of the exact SmartCMP script definition selected by an embedded script-editor page Context."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - modify current SmartCMP script
  - improve current script
  - update script content
  - 修改当前脚本
  - 完善当前脚本
  - 优化当前脚本

use_when:
  - User is interacting from a SmartCMP script editor and asks to change the current saved script
  - User wants a complete replacement script body for manual copying into CMP

avoid_when:
  - User wants to execute a script
  - User wants to save, publish, delete, or otherwise write a script through CMP APIs
  - No SmartCMP script editor Context is active

tool_current_name: "smartcmp_read_current_script_definition"
tool_current_description: "Read the exact saved script definition bound to the active SmartCMP script-editor Context. The tool uses the request user's session and server-owned object scope, takes no script ID, and never writes to CMP."
tool_current_entrypoint: "scripts/read_current_script.py:read_current_script"
tool_current_groups:
  - cmp
  - script-designer
tool_current_capability_class: "provider:smartcmp"
tool_current_priority: 115
tool_current_result_mode: "llm"
tool_current_parameters: |
  {
    "type": "object",
    "properties": {},
    "additionalProperties": false
  }
---

# script-designer

Read the current saved SmartCMP script and produce user-directed replacement content.

## Workflow

1. Always call `smartcmp_read_current_script_definition` before analyzing or changing the script. Never ask the user for a script ID that is already bound by Context.
2. Use the returned script type, parameters, properties, form content, resource types, and complete current body as the source of truth. In this first phase, all fields except `content` are read-only compatibility context.
3. Apply only the requested behavior. Preserve unrelated logic, public entrypoints, parameter names, return contracts, runtime compatibility, and error semantics.
4. Return the complete updated script body in one fenced code block. Never return only a diff, partial snippet, or content containing ellipsis placeholders.
5. Do not propose replacement values for `params`, `properties`, `formContent`, or other script-definition metadata. If the requested behavior requires one of those fields to change, state that the current Skill only generates `content` and identify the unmet metadata change separately.
6. State that the result is for manual review and copying into the CMP script `content` field. Do not claim that the script was saved, published, or executed.

## Safety

- Do not call POST, PUT, PATCH, DELETE, publish, execute, or task APIs.
- Do not invent Provider SDK calls, endpoints, credentials, or runtime variables.
- Preserve the current script language and compatibility constraints unless the user explicitly requests a migration.
