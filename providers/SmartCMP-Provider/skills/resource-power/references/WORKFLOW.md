# Resource Power Workflow

Use this workflow when the user wants to start or stop an existing SmartCMP cloud resource or cloud host.

## Resolve Targets First

1. If the user already gave a SmartCMP `resource_id`, use it directly.
2. If the user only gave a display name such as `mysqlLinux2`, call `smartcmp_list_resources` first.
3. Match the user's chosen row to the metadata item's `id`.
4. If multiple rows have the same name, do not guess. Ask the user to choose the correct one.

## Check Current Status

The resource list output now shows each item's current status.

- Prefer to stop resources that are currently `started`, `running`, or equivalent active states.
- Prefer to start resources that are currently `stopped`, `powered_off`, or equivalent inactive states.
- If the target already matches the requested state, tell the user no power change is needed before submitting another action.

## Execute the Power Action

Call `smartcmp_operate_resource_power` with:

- `action=start` for 开机 / 启动
- `action=stop` for 关机 / 停止
- `resource_ids` set to one or more real SmartCMP resource IDs

The tool submits this immediate-operation payload shape:

```json
{
  "operationId": "start or stop",
  "resourceIds": "id1 or id1,id2",
  "scheduledTaskMetadataRequest": {
    "cronExpression": "",
    "cycleDescription": "",
    "cycled": false,
    "scheduleEnabled": false,
    "scheduledTime": null
  }
}
```

## Follow-Up

- If the user asks whether the action succeeded, refresh the resource list or use `smartcmp_analyze_resource_detail` for the same resource ID.
- Treat SmartCMP submission as asynchronous unless the platform response clearly says the resource is already in the target state.
