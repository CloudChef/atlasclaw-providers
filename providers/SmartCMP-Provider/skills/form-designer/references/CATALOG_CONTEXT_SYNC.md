# Service Catalog Context Sync

Use this reference when generating SmartCMP form JSON that reads service-catalog request-page context, syncs hidden submit fields, or builds JSON-string values from fields such as 业务组, 所有者, 应用系统, or 名称.

## Service catalog context display values

When generating dynamic JavaScript snippets that read SmartCMP service catalog
request-page context, start from the fixed backend/UI field declarations in
`/platform-api/catalogs/<id>.exts.field` instead of guessing from display text.
The live request-page catalog metadata exposes `exts.field` as a list whose
stable identity is `exts.field[].id`; `exts.field[].name` is also important
because Angular scope data and rendered DOM attributes may use that name form.
Those declared id/name keys identify controls; they are not always the values
that should be submitted.

When the generated JSON string contains display-label entries such as `业务组`,
`所有者`, `应用系统`, or `名称`, prefer human-readable display names in
`out[...].value`. For these display-label outputs, never submit the stable
control ID/UUID as the value. If a display name is not available yet, keep the
previous complete `lastGood` JSON string or the field's pending default while
the timer continues resolving; do not publish an ID fallback.

| Context label | `exts.field[].id` | `exts.field[].name` | Fixed display-value key for `FIELD_SPECS.keys` | Do not submit from |
| --- | --- | --- | --- | --- |
| Business group / 业务组 | `businessGroup` | `BusinessGroup` | `catalogServiceRequest.exts.businessGroup.name` | `businessGroupId`, `businessGroup`, `BusinessGroup` |
| Application system / 应用系统 | `projects` | `Projects` | `catalogServiceRequest.exts.project.name` | `projectId`, `projects`, `Projects`, `project` |
| Owner / 所有者 | `owners` | `Owners` | `catalogServiceRequest.exts.owner.name` | `ownerId`, `owner`, `owners`, `Owners`, `userId` |
| Name / 名称 | `name` | `Name` | `name` | `Name`, `requestName`, `deploymentObj.name` |

Keep browser context reads separate from request submission contracts. Catalog
instructions may still require submitted fields such as `businessGroupName` and
`name`; do not replace the request contract with UI context keys. These
submission keys can differ from the keys used to read page context.

For the Linux VM catalog
`f3a4149b-cfbf-446a-a340-512a304014f2`, the authoritative API metadata is
`exts.field`: `businessGroup/BusinessGroup`, `projects/Projects`,
`owners/Owners`, and `name/Name`. These are control declarations. For submitted
display JSON, fix the business group key to
`catalogServiceRequest.exts.businessGroup.name` and the owner key to
`catalogServiceRequest.exts.owner.name`. Fix the application-system key to
`catalogServiceRequest.exts.project.name`. Fix the name key to `name`. Do not
add secondary scope keys unless a later catalog inspection proves that exact
catalog uses those paths.

Do not invent a new display extraction algorithm in the dynamic JavaScript.
The working `test-ip-form.json` helper chain already knows how to read SmartCMP
platform values. Keep its `text`, `clean`, `direct`, `pick`, `deep`, `selected`,
`byLabel`, `roots`, `valueOf`, `valid`, `existing`, `resolve`, `hideUi`, and
`write` helpers. For display-label outputs, each `valueOf` candidate list must
contain the fixed display path for that output only. ID-bearing keys such as
`businessGroup`, `BusinessGroup`, `businessGroupId`, `owner`, `owners`,
`Owners`, `ownerId`, `projects`, `Projects`, `projectId`, `Name`, and
`requestName` are control identifiers or aliases, not submitted display values.
Do not publish UUID-like or ID-like values from model/input fallbacks for
`业务组`, `所有者`, `应用系统`, or `名称`; keep resolving until the fixed display
path or DOM selected text is found.

Fixed service catalog context labels are sufficient for this pattern. If the
user asks for a form JSON that only combines fixed labels from the table above
such as 业务组, 应用系统, 所有者, or 名称, generate the form directly from the
fixed keys. Do not read the service catalog first.
Do not ask the user for existing form schema.
Do not ask for field IDs, field keys, or schema versions.
Tool or catalog lookup failure must not block JSON generation for these fixed context fields.
Continue with the fixed keys and return the JSON text.

## Dynamic JavaScript context sync pattern

For hidden fields that derive values from the service catalog request page:
Use the `test-ip-form.json` expression skeleton as the source of truth, and
copy the maintained fixed template from
`references/catalog-context-expression.js` for service-catalog header fields.
The template is marked `CATALOG_CONTEXT_SYNC_TEMPLATE_V1`. Do not hand-write
another JavaScript lookup function for these header-field sync forms.
Do not invent a new runtime lookup algorithm.
Do not try to read `test-ip-form.json` from disk. The maintained reusable file
for this skill is `references/catalog-context-expression.js`; `test-ip-form.json`
is only a historical behavior reference in these instructions.
Change only `KEY` and the `FIELD_SPECS` entries for the current target. Each
`FIELD_SPECS` entry owns its submitted output label, runtime state name, key
list, and DOM label list.
`FIELD_SPECS` may contain one entry or many entries. The template loops over
the array and only publishes a new JSON string after every configured entry has
resolved a non-empty value.
The only required behavior change from `test-ip-form.json` is the final submit format: backend-facing field values must be valid JSON strings produced by `JSON.stringify(out)`.

- For strict display-value sync of service-catalog header fields, use one
  display source path per output and let DOM label fallback handle renderer
  variation. Do not mix ID-bearing fields into the same `keys` list. For
  example, map `业务组` to `catalogServiceRequest.exts.businessGroup.name` and
  map `所有者` to `catalogServiceRequest.exts.owner.name`; do not add
  `businessGroupId`, `businessGroup`, `BusinessGroup`, `ownerId`, `owner`,
  `owners`, or `Owners` as fallback keys for these display outputs.
- For the common submitted payload `{"业务组":{"value":"..."}, "所有者":{"value":"..."}, "应用系统":{"value":"..."}, "名称":{"value":"..."}}`,
  use this exact fixed spec:
  `FIELD_SPECS=[{state:'businessGroupName',output:'业务组',keys:['catalogServiceRequest.exts.businessGroup.name'],labels:['业务组','BusinessGroup']},{state:'ownerName',output:'所有者',keys:['catalogServiceRequest.exts.owner.name'],labels:['所有者','Owner','Owners']},{state:'projectName',output:'应用系统',keys:['catalogServiceRequest.exts.project.name'],labels:['应用系统','Projects']},{state:'requestName',output:'名称',keys:['name'],labels:['名称','Name']}]`.
  A generated spec with `keys:['businessGroup']`, `keys:['BusinessGroup']`,
  `keys:['owner']`, `keys:['owners']`, `keys:['Owners']`, `keys:['projects']`,
  `keys:['Projects']`, `keys:['Name']`, or `keys:['requestName']` is wrong for
  this payload because those keys locate controls/aliases rather than the fixed
  submitted display values.
- The maintained `references/catalog-context-expression.js` template already
  contains the four universal service-catalog header fields: `业务组`, `应用系统`,
  `所有者`, and `名称`. Keep those `FIELD_SPECS` entries for the common full
  header-sync form, and change only `KEY` for the target hidden submit field.
- For an EIP `test-eip` request with field `mixture` combining `应用系统`, `名称`, and `所有者`,
  set `KEY='mixture'` and use this exact spec:
  `FIELD_SPECS=[{state:'projectName',output:'应用系统',keys:['catalogServiceRequest.exts.project.name'],labels:['应用系统','Projects']},{state:'requestName',output:'名称',keys:['name'],labels:['名称','Name']},{state:'ownerName',output:'所有者',keys:['catalogServiceRequest.exts.owner.name'],labels:['所有者','Owner','Owners']}]`.
  This request has enough information to generate a complete new SmartCMP schema.
  Do not call catalog query, do not call `smartcmp_read_form_schema`, and do not
  refuse because `references/catalog-context-expression.js` contains all four
  universal service-catalog header fields by default.
- If the user asks for a smaller subset, remove only the unneeded `FIELD_SPECS`
  entries while preserving the same helper chain and fixed display paths.
- Do not copy `test-ip-form.json` verbatim. It is a working reference for the
  helper chain only, not a reusable field contract. Unless the user is asking
  for that exact IP form, the generated expression must not leave
  `KEY='infoblox_ip_attr'`, `APP_OUTPUT_KEY='应用服务器'`, or
  `OWNER_OUTPUT_KEY='责任人'` in place. Service-catalog header sync forms must
  contain `CATALOG_CONTEXT_SYNC_TEMPLATE_V1` and a target-specific
  `FIELD_SPECS` array.
- The template is allowed to stay moderately broad in its DOM/scope readers
  (`roots`, `byLabel`, `selected`) because SmartCMP renderers vary. The fixed
  part is the output contract, helper chain, timer/write behavior, and the
  per-field key-list structure. Do not replace these helpers with a shorter
  one-off expression.
- Dot-path keys such as `a.b.c` must be resolved by walking object properties;
  do not treat them as literal flat keys only.
- In DOM fallback, read visible selected text before `input` or `textarea` values.
  SmartCMP select widgets may render a hidden/search input before the
  selected label, so input-first selectors can return empty strings.
- In `roots`, catch errors per DOM node. A single controller/scope lookup
  failure must not abort scanning the rest of the page.
- Single-field example:
  `FIELD_SPECS=[{state:'requestName',output:'名称',keys:['name'],labels:['名称','Name']}]`.
- Multi-field example:
  `FIELD_SPECS=[{state:'projectName',output:'应用系统',keys:['catalogServiceRequest.exts.project.name'],labels:['应用系统','Projects']},{state:'requestName',output:'名称',keys:['name'],labels:['名称','Name']},{state:'ownerName',output:'所有者',keys:['catalogServiceRequest.exts.owner.name'],labels:['所有者','Owner','Owners']}]`.
  The fixed-label subset can contain one, two, three, or four `FIELD_SPECS` entries
  chosen from `业务组`, `应用系统`, `名称`, and `所有者`.
  Do not answer that `CATALOG_CONTEXT_SYNC_TEMPLATE_V1` only supports custom
  placeholder fields; the maintained template supports the four universal
  service-catalog header fields by default.
- Put the dynamic function under `config.value` with `source: "mock"`,
  `method: "mock"`, and a one-line `expression` string.
- Do not put dynamic source metadata in a top-level `value` key. It belongs
  under the field's `config.value`.
- The submitted auto-sync value must remain a string in `model[KEY]`, the
  hidden input, and Angular `ngModel`. Build a plain JavaScript object named
  `out` and then assign `var v=JSON.stringify(out)`, exactly like
  `test-ip-form.json`. For nested label values, use
  `out[APP_OUTPUT_KEY]={value:app}` and `out[OWNER_OUTPUT_KEY]={value:owner}`;
  then write the string from `JSON.stringify(out)` to `model[KEY]`.
- Do not build pseudo-JSON strings with manual braces, manual quotes, string
  concatenation, Chinese punctuation separators, or template fragments. The
  backend must receive a valid JSON string produced by `JSON.stringify`.
- Do not return a JavaScript object or array from the expression, and do not set
  the hidden submit field to `type: "object"` or `type: "array"`. Even when the
  backend expects "JSON", the form field value is a string containing that JSON
  text.
- Keep Chinese labels and Chinese punctuation as literal UTF-8 text in the
  schema and JavaScript expression. Do not manually convert Chinese labels or values to Unicode escape sequences.
  Do not use `escape`, `unescape`, `charCodeAt`, `String.fromCharCode`, or
  hand-written Unicode escape conversions for Chinese display text.
- Use a rendered string field with `widget.id: "string"`, not `widget.id:
  "hidden"`, when the value must be submitted but not shown. Do not set `hidden: true` or `condition: "1 === 2"` on the auto-sync field; SmartCMP
  compiles `condition` to `ng-if`, so the field's `config.value.expression`
  will not execute if the field is not rendered. Hide the field from users with
  `hideTitle`, `hideTitleText`, `notitle`, and the expression's `hideUi`
  DOM/CSS logic after the input exists.
- Add `default: "AUTO_SYNC_PENDING"` so the field is initialized before the
  dynamic value is resolved.
- Add the submit field and `schemaFormValid` to root `fieldsets`; unregistered
  properties may not be rendered or submitted by the request page.
- Start the function as `function(model, sourceParams, schema, unused, cfg)` so
  it can read current model values, source parameters, schema metadata, and
  renderer config.
- Keep the `valueOf` search order from `test-ip-form.json`: scan roots,
  `params`, `resourceBundleParams`, `genericRequest.processForm`, deep
  `resourceSpecs`, then DOM labels. For strict display outputs, the key list
  must contain only the fixed display path for that output. For the Linux VM
  catalog, that means `业务组` uses only
  `catalogServiceRequest.exts.businessGroup.name`, and `所有者` uses only
  `catalogServiceRequest.exts.owner.name`, `应用系统` uses only
  `catalogServiceRequest.exts.project.name`, and `名称` uses only `name`.
  Declared control keys such as `businessGroup`, `BusinessGroup`, `projects`,
  `Projects`, `owners`, and `Owners` are only useful for locating rendered
  controls or metadata; do not include them in display-output `FIELD_SPECS.keys`.
- Generate separate `valueOf` calls with separate key lists for each output.
  Do not write a generic `valueOf(name, rootsList)` that ignores `name` and
  scans one hard-coded field sequence.
- Keep per-field state under `window` using a key derived from the hidden field
  id. Cache the last complete value so transient empty renders do not erase a
  previously resolved value.
- Do not cache or return incomplete values such as `{业务组：，所有者：}`.
  Implement a `valid` or equivalent completeness check and only update
  `lastGood` when every required source value is present.
- Do not generate a shallow one-shot expression that only checks
  `sourceParams` and `model` once. The expression must include helper functions
  equivalent to `deep`, `byLabel`, and `roots` from `test-ip-form.json`, so it
  can read nested Angular scopes, `resourceSpecs`, `params`,
  `genericRequest.processForm`, and rendered DOM labels.
- Validate the final one-line JavaScript function for syntax before returning
  it. A missing brace inside `try/catch` prevents `config.value.expression`
  from executing at all, so the field stays empty or `AUTO_SYNC_PENDING`.
- Never abbreviate the expression with a literal `...` or any placeholder.
  The schema must contain the complete executable JavaScript function. A
  truncated expression is invalid JavaScript and SmartCMP will keep the field's
  default value.
- The `roots` helper must start with `[sourceParams, schema, cfg, model]` and
  then collect Angular `catalog-form`, `.catalog-form`, and `[ng-controller]`
  controllers, isolate scopes, scopes, `vm`, and `$ctrl` values. Do not
  implement `roots` as only a `$parent` walk from `cfg.$scope`; some SmartCMP
  renderers do not pass `cfg.$scope`, and the needed data may live on catalog
  controllers instead.
- Read `params`, `resourceBundleParams`, `genericRequest.processForm`, and deep
  `resourceSpecs` for every source value before falling back to DOM labels.
- `byLabel` must query rendered form blocks by label text, like
  `.form-group`, `.ant-form-item`, `.schema-form-default-item`, and
  `.schema-form-ui-select`; do not implement `byLabel` as another scope-key
  lookup over `businessGroupName` or `ownerName`.
- Keep `test-ip-form.json`'s DOM `selected` helper behavior for `select`
  elements: read the selected option text before using `el.value`.
- If a target renderer is proven to reset the model after a valid value is
  resolved, a model getter/setter guard may be added, but do not add one by
  default when following `test-ip-form.json`.
- Use `setInterval` to re-resolve context after async catalog controls finish
  rendering, and clear any previous interval before starting a new one, as in
  `test-ip-form.json`.
- Write the resolved value into `model[KEY]`, update the hidden input value,
  dispatch bubbling `input` and `change` events, and call Angular `ngModel`
  `$setViewValue` plus `$applyAsync` when available.
- Find the target input with `[name="'+KEY+'"],#'+KEY` first, then optionally
  fall back to `input[ng-model*="'+KEY+'"]` or `textarea[ng-model*="'+KEY+'"]`.
  Do not rely only on `[ng-model*="...KEY..."]` substring selectors; SmartCMP
  frequently uses generated ngModel paths that do not contain the field id.
- Find the Angular model controller from the field element with
  `angular.element(e).controller('ngModel')`. Do not use `scope.$$childHead[KEY]`
  or sibling-scope property guesses; those are not ngModel controllers.
- Return the existing valid value while required context is incomplete. Do not
  return placeholder labels, loading text, or partial JSON.
