# Decomposition Guidelines

Use this file when a descriptive requirement needs to be turned into multiple CMP request candidates.

## Good Decomposition Signals

- The request clearly implies more than one resource type.
- There are explicit dependencies such as app plus database, app plus storage, or app plus network exposure.
- The requirement includes environment, expected workload, or resilience hints that can guide service selection.
- The user gives per-item differences using ordinal references such as first, second, third, fifth, or sixth.

## Not A Decomposition Signal By Itself

- Quantity alone for one resource type is not enough.
- If the user wants multiple instances of the same resource type with the same parameters, keep it in the plain `request` workflow.

## Ordinal And Quantity Validation

- If the user gives a total instance count and also gives ordinal per-item details, validate that the ordinal references fit within that count.
- If the numbering is non-consecutive or out of range, ask a clarification question before creating draft sub-requests.
- Do not silently renumber the user's intent.
- Do not invent missing instances just to make the numbering contiguous.

## Stop And Leave For Manual Review When

- Core business purpose is unclear.
- No matching CMP catalog item can be found.
- Required identifiers such as business group or application are unavailable.
- High-cost or production-sensitive components depend on guessed values.
- Instance quantity conflicts with the user's ordinal references.

## Preferred Output Shape

- one sub-request per CMP catalog item
- assumptions listed separately
- unresolved fields listed explicitly
- operator follow-up items stated in plain language
