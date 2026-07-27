---
name: "component-script-designer"
description: "Use when reading or modifying a script file under `scripts/` for the exact SmartCMP component selected by an embedded component-editor page Context, with rules routed by component resource type."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - modify current component script
  - improve component file
  - update blueprint component script
  - 修改当前组件脚本
  - 完善组件库脚本
  - 优化组件文件

use_when:
  - User is interacting from a SmartCMP blueprint component editor
  - User wants a complete replacement for one current component script file under `scripts/`

avoid_when:
  - User wants to save, publish, upgrade, import, export, or delete a component
  - User wants to create an unrelated component outside the current page Context

tool_current_name: "smartcmp_read_current_component_file"
tool_current_description: "Read the exact current SmartCMP component bound to page Context, list its files under `scripts/`, and return one complete selected script file. If file_path is omitted, a sole script file is selected automatically; multiple script files are listed for exact selection. The tool never writes to CMP."
tool_current_entrypoint: "scripts/read_current_component_file.py:read_current_component_file"
tool_current_groups:
  - cmp
  - component-script-designer
tool_current_capability_class: "provider:smartcmp"
tool_current_priority: 115
tool_current_result_mode: "llm"
tool_current_parameters: |
  {
    "type": "object",
    "properties": {
      "file_path": {
        "type": "string",
        "description": "Exact path under `scripts/` from the current component's blueprintFiles list. Omit when the component contains only one script file."
      }
    },
    "additionalProperties": false
  }
---

# component-script-designer

Read one file from the current saved component and produce a complete replacement for manual copying.

## Workflow

1. Call `smartcmp_read_current_component_file`. If several files are returned and the user did not identify one, ask for the exact listed `file_path`; never guess.
2. Use `componentFamily` to select the matching rules in `references/component-script-rules.md`.
3. Apply only the requested change and preserve the selected file's entrypoints, parameters, return shape, runtime version, line-ending expectations, and unrelated logic.
4. Return the exact file path and the complete updated file in one fenced block. Never return only a diff, partial snippet, or ellipsis placeholder.
5. State that the output is for manual review and copying into CMP. Do not claim that the component was saved, published, upgraded, or deployed.

## Type Routing

- `exporter`: Prometheus exporter and monitoring-agent components.
- `integration`: `resource.integration.*`.
- `software`: `resource.software.*`.
- `resource`: `resource.iaas.*`, `resource.paas.*`, and `resource.caas.*`.
- Unknown families fail closed; do not apply a different component family's assumptions.

## Safety

- No component write, publish, upgrade, import, export, or execution APIs.
- Do not invent third-party endpoints, cloud SDK fields, runtime variables, or credentials.
- Read `references/component-script-rules.md` before producing component code.
