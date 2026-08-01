"""AtlasClaw Tool adapters for SmartCMP form reads and schema design."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Literal


_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from _atlasclaw_adapter import (  # noqa: E402
    RunContext,
    embedded_object_id,
    execute,
    tool_error,
    tool_result,
)
from smartcmp_provider.forms.design import visible_warnings  # noqa: E402
from smartcmp_provider.models.forms import (  # noqa: E402
    FormDesignInput,
    FormReadQuery,
)
from smartcmp_provider.services.forms import (  # noqa: E402
    design_form as design_form_operation,
    read_form as read_form_operation,
)


async def read_current_form(ctx: RunContext[Any]) -> dict[str, Any]:
    """Read the saved form bound to the current SmartCMP page Context."""

    try:
        form_id = embedded_object_id(
            ctx,
            expected_object_type="form_definition",
        )
        if not form_id:
            raise ValueError(
                "This tool requires an active SmartCMP form page Context."
            )
        result = await execute(
            ctx,
            read_form_operation,
            FormReadQuery(form_id=form_id),
            request_cookie_only=True,
        )
        return tool_result(
            result,
            summary=f"Loaded current SmartCMP form {result.name or form_id}.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def read_form(
    ctx: RunContext[Any],
    form_url: str,
) -> dict[str, Any]:
    """Read one current-instance SmartCMP form URL without writing it."""

    try:
        current_id = embedded_object_id(
            ctx,
            expected_object_type="form_definition",
        )
        result = await execute(
            ctx,
            read_form_operation,
            FormReadQuery(
                form_id=current_id or "",
                form_url=form_url,
            ),
            request_cookie_only=current_id is not None,
        )
        return tool_result(
            result,
            summary=f"Loaded SmartCMP form {result.name or result.form_id}.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def design_form(
    ctx: RunContext[Any],
    mode: Literal["new", "modify", "regenerate"],
    schema_json: str | None = "",
    form_url: str | None = "",
    change_summary: str | None = "",
    catalog_fields_json: str | None = "",
    value_expressions_json: str | None = "",
    requested_fields_json: str | None = "",
) -> dict[str, Any]:
    """Build a complete replacement schema from AtlasClaw Tool input.

    AtlasClaw may materialize omitted optional string properties as ``None``.
    This Adapter normalizes that external Tool boundary while keeping the Provider
    model strict and does not perform a CMP write.
    """

    try:
        current_id = embedded_object_id(
            ctx,
            expected_object_type="form_definition",
        )
        form_id = current_id or ""
        normalized_form_url = form_url or ""
        result = await execute(
            ctx,
            design_form_operation,
            FormDesignInput(
                mode=mode,
                schema_json=schema_json or "",
                form_id=form_id,
                form_url=normalized_form_url,
                change_summary=change_summary or "",
                catalog_fields_json=catalog_fields_json or "",
                value_expressions_json=value_expressions_json or "",
                requested_fields_json=requested_fields_json or "",
            ),
            request_cookie_only=current_id is not None,
        )
        final_output = _format_design_output(result)
        payload = tool_result(
            result,
            summary=final_output,
        )
        # AtlasClaw's provider-neutral ``final_user_output`` contract bypasses
        # model summarization and Tool-evidence truncation for exact artifacts.
        payload["final_user_output"] = final_output
        return payload
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


def _format_design_output(result: FormDesignResult) -> str:
    """Render the complete replacement schema required by ``tool_only_ok``."""

    source = result.source
    object_id = str(source.get("formId") or "").strip()
    object_name = str(source.get("name") or "").strip()
    if not object_name:
        object_name = (
            "New SmartCMP form draft" if not object_id else "SmartCMP form"
        )
    if not object_id:
        object_id = "N/A (new unsaved draft)"

    schema_text = json.dumps(
        result.form_schema,
        ensure_ascii=False,
        indent=2,
    )
    longest_fence = max(
        (len(match.group(0)) for match in re.finditer(r"`+", schema_text)),
        default=0,
    )
    fence = "`" * max(3, longest_fence + 1)
    validation = [
        "- Schema normalization and structural validation completed."
    ]
    validation.extend(
        [f"- Risk: {warning}" for warning in visible_warnings(list(result.warnings))]
        or ["- Risks: No additional schema warnings were reported."]
    )
    return "\n".join(
        [
            "## 1. Current Object",
            f"- Name: {object_name}",
            f"- ID: {object_id}",
            "",
            "## 2. Copy Target",
            "- Copy the JSON below into the form definition's `content.schema` field.",
            "",
            "## 3. Change Summary",
            result.changeSummary,
            "",
            "## 4. Complete Replacement JSON",
            f"{fence}json\n{schema_text}\n{fence}",
            "",
            "## 5. Validation and Risks",
            *validation,
            "",
            "## 6. Save Status",
            "- Not saved. This Tool did not write, publish, or update anything in CMP.",
            "- Review the complete JSON and copy it back to the SmartCMP form editor manually.",
        ]
    )
