# SmartCMP Component Script Rules

This runtime reference is a concise page-interaction projection of the canonical component authoring Skills under:

- `smartcmp-components/component-skills/exporter-component`
- `smartcmp-components/component-skills/integration-component`
- `smartcmp-components/component-skills/resource-component`
- `smartcmp-components/component-skills/software-component`

Those project Skills remain the source for full component creation. This page Skill only updates one existing saved file, so it preserves the current component contract and applies the following type-specific rules.

## Common Rules

- Preserve current file language, public entrypoints, lifecycle parameter names, return shape, execution location, and runtime compatibility unless explicitly changed.
- Modify only the selected existing file. Do not silently create a second implementation, move behavior to another file, or assume that related lifecycle/form/manifest files will also be changed.
- Treat the current component metadata and selected file as the compatibility boundary. If a requested change requires another file or an unprovided external contract, report that dependency instead of inventing it.
- Never introduce credentials, fixed customer endpoints, unsafe logging, or a second parallel implementation path.
- Do not invent an API, SDK method, status, runtime property, or SmartCMP context field.
- Preserve input parameter names and defaults, observable stdout/set-output keys, JSON return keys, exit status semantics, retry behavior, and idempotency expectations.
- Validate only external inputs and documented runtime boundaries. Do not swallow failures or turn an error into a successful empty result.
- Keep source comments, docstrings, and log messages in English.
- Return one complete replacement file with no omitted sections.

## Exporter

- Exporter lifecycle scripts execute through `script.script_runner.tasks.run` on `host_agent`; preserve that execution location and read lifecycle inputs from environment variables rather than Cloudify `ctx`.
- Existing Python scripts must remain Python 2.7 compatible unless the component explicitly proves a newer runtime.
- Do not use f-strings, `subprocess.run`, `pathlib`, type annotations, or `json.JSONDecodeError` in Python 2.7 files.
- Python entry scripts keep `from __future__ import print_function`, read parameters with the existing environment/get-parameters helper, and emit runtime values through the existing `set_output key=value` stdout contract.
- Preserve install/start/stop versus add/delete monitoring-target responsibilities. Keep the existing config format, service name, config path, listen address/port, target parameter names, and systemd invocation compatible.
- Preserve the distinction between metric value `0`, no data, and collection failure.
- Keep monitoring target identity and labels stable; do not broaden a query beyond the current resource.
- Never print target credentials, complete target configuration, or command lines containing secrets.

## Integration

- Integration scripts operate on third-party connection configuration and action parameters; they do not write Resource runtime properties unless the current contract already requires it.
- Python operation scripts expose `main()`, parse `connectionConfig` and `params` from their established environment inputs, and return a JSON-serializable result with the existing output keys.
- Integration scripts do not import or read `pysdx ctx`. Connection settings come from `connectionConfig`; per-call business inputs come from `params`.
- Centralize CMP-to-third-party field mapping in the existing transformer/helper layer.
- Keep callback, web-operation, Task, and ordinary lifecycle semantics distinct.
- Preserve debug-mode behavior and validate required real connection fields before constructing an API client. Debug output may report whether a secret exists but must not reveal the secret, token, cookie, complete `connectionConfig`, or signed URL.
- Preserve existing timeout, HTTP error, third-party status mapping, callback/execution ID, and exception-to-result semantics.
- If an external API contract is absent, leave a clear TODO instead of fabricating behavior.

## Software

- Software lifecycle scripts execute through `script.script_runner.tasks.run` on `host_agent`; preserve the current Shell/Ansible execution model and environment-variable input names.
- Install/start/stop scripts keep their existing non-zero exit behavior on failure, avoid printing credentials, and remain idempotent where the current lifecycle contract is idempotent.
- Keep install, start, stop, and collect responsibilities separate.
- Python collection scripts remain Python 2.7 compatible and preserve the existing `set_output <key>=<json>` stdout contract; distinguish empty inventory from collection failure.
- Do not silently move execution to the central agent or bind a software component to a CloudEntry.

## IaaS / PaaS / CaaS Resource

- Resource lifecycle scripts execute on `central_deployment_agent` through the existing `sdx.resource_manager.operations.run_script` contract and use the component's established `pysdx ctx` access pattern.
- Preserve the split between Day-1 values read from `ctx.node.properties.resource_config` and Day-2 target values supplied by the current operation inputs. Do not replace a requested Day-2 value with the old Day-1 value.
- Preserve the real `resourceType`, Provider scope, relationships, stable external ID, runtime facts, and current lifecycle contract.
- Preserve existing runtime-property keys, relationship targets, stable external IDs, returned status shape, and provider SDK argument names. Write runtime properties only after the Provider operation succeeds.
- Day-1 parameters, Day-2 parameters, query/import behavior, monitoring, billing, and policy evidence have separate semantics; do not mix them in one fallback path.
- Keep provider/resourceType gates exact, propagate Provider failures, and do not turn missing evidence into a fabricated successful resource state.
- Do not log connection configuration, complete request/response bodies, signed URLs, or secrets.
- An absent cross-repository capability must remain an explicit limitation, not an unreachable placeholder.
