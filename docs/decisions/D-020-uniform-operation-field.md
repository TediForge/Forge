# D-020: `operation` Is Mandatory on Every Tool

> **Partially superseded by D-021.** The placeholder exception below is
> removed: no registered operation may return `NOT_IMPLEMENTED`. See
> [D-021](./D-021-no-registered-placeholder-operations.md).

- **Status:** Accepted
- **Date:** 2026-11-10
- **Owner:** Orchestrator
- **Partially supersedes:** D-019 by adding the single-capability case and the mandatory-field rule.
- **Related:** [D-019](./D-019-one-tool-per-domain-one-skill.md), [D-009](./D-009-one-word-tool-contract.md), [Orchestrator Runtime §9](../architecture/orchestrator-runtime.md), [Skill taxonomy](../references/skills.md)

## Context

D-019 established one tool per domain, operations inside the tool, and one
`SKILL.md` per registered tool. It did not require `operation` on
single-capability tools. This left special cases such as `calculate(expression)`
and `clock(timezone)` alongside operation-based tools such as `data` and
`video`.

The public contract should have one shape: the model always selects an
operation, every skill documents an operations table, and every Action ID is
associated with an operation. This also makes future capability growth an
enum-and-skill update rather than a new tool registration.

## Decision

**Every registered tool requires an `operation` argument with a non-empty
enum.**

- A one-capability tool has a single-value enum, named for its behavior:
  `calculate(operation="evaluate")`, `clock(operation="now")`,
  `transcribe(operation="audio")`, and `speak(operation="text")`.
- A multi-capability tool has a multi-value enum, such as
  `data(operation="table"|"sql"|...)` or
  `search(operation="web"|"image"|"news")`.
- The schema includes `operation` in both `properties` and `required`.
  Handlers dispatch on that value, and each matching skill has one operations
  table with a Status column.
- Every operation has a stable `tool(operation=<name>)` Action ID row.
- A known but unavailable operation may be registered as a placeholder. It
  returns a typed `NOT_IMPLEMENTED` result, performs no work, and is labeled
  `placeholder` in the skill and Action ID catalog. It must not return
  success-shaped fabricated data.
- Every tool has exactly one skill folder, independent of how many
  operations it exposes.

Operations are registered only when they are part of the public tool
contract. The current tool families and operation statuses are recorded in
[Orchestrator Runtime §9](../architecture/orchestrator-runtime.md).

## Consequences

**Positive**

- The model always supplies the same required discriminator field.
- Adding a capability changes an existing enum, handler, skill, and Action ID
  list; it does not add a model-visible tool or skill folder.
- A placeholder is an honest, testable response rather than a guessed
  substitute operation.
- The tool schema, skill table, and Action ID catalog can be cross-checked
  mechanically.

**Costs**

- Every registered tool schema, handler, skill, and Action ID entry must
  carry the operation shape, including one-operation tools.
- Placeholder registrations add visible enum choices; their descriptions and
  skills must clearly state that they do not execute work.
- Public callers must migrate to provide the required `operation`.

## Alternatives considered

1. **Keep single-capability tools without `operation`.** Rejected because it
   creates an exception to the D-019 domain-operation contract.
2. **Add operations only when a second capability is implemented.** Rejected
   because it makes future changes unexpectedly alter existing tool shapes.
3. **Use a generic value such as `default` or `run`.** Rejected because
   operation names should describe the behavior, such as `now` or `evaluate`.
4. **Omit known future operations.** Rejected when the operation is an
   explicitly planned part of the contract; use a placeholder instead, with
   `NOT_IMPLEMENTED` and no side effects.

## Enforcement

- `tests/unit/test_tool_operations_audit.py::test_every_tool_has_operation`
  checks every registered schema requires a non-empty operation enum.
- `tests/unit/test_tool_operations_audit.py::test_operation_enum_matches_skill`
  compares every operation enum with its skill table.
- `tests/unit/test_action_contract.py::test_every_operation_has_action_id`
  checks every operation has a catalog entry.
- `tests/unit/test_action_contract.py::test_placeholders_return_not_implemented`
  calls each cataloged placeholder and checks its typed failure.
- `tests/unit/test_one_skill_per_tool.py` checks one matching skill folder and
  one `SKILL.md` per registered tool.

## See also

- [D-019: One tool per domain, operations inside](./D-019-one-tool-per-domain-one-skill.md)
- [D-009: One-word tool contract](./D-009-one-word-tool-contract.md)
- [Skill taxonomy and quality standard](../references/skills.md)
