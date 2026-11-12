# D-006: CamelCase Wire Contract and Central Tool Validation

- **Status:** Accepted
- **Owner:** Orchestrator
- **Related:** [Orchestrator Runtime](../architecture/orchestrator-runtime.md), [Wire Contract](../references/wire-contract.md), [D-004](./D-004-external-tools-two-phase-resume.md)

## Context

The public API mixed snake_case and camelCase fields, while internal Python
code and tool schemas have different naming needs. Tool arguments also crossed
multiple callers before reaching local or MCP handlers.

## Decision

Public JSON fields are camelCase and internal Python names are implementation
details mapped through `CamelBaseModel` aliases. The only deliberate wire
exception is `call_id` on `FunctionCall`, because Responses API clients use
that literal correlation field. Legacy snake_case request aliases remain
accepted where needed, but camelCase is the canonical OpenAPI name.

`ToolExecutor` validates every parsed argument object against the registered
JSON Schema before dispatch. It returns typed `ToolResult` failures rather
than raising validation exceptions; failures emit `action.invalid_arguments`
with tool/run/tenant identity and schema path, never raw arguments.

Attachment text is limited to 4,000 characters per file and 12,000 total;
conversation history is the last ten messages, with 2,000 characters per
message and 8,000 total. These caps bound prompt growth. Attachment content
and transient history are excluded from checkpoint exports to avoid retaining
user file content or conversation bodies. Suspended checkpoints may retain a
sanitized history snapshot with attachment names only to support resume.

Only internal tool executions count toward `max_tool_calls`. Caller-owned
external calls suspend for the caller to execute and therefore are not engine
tool executions.

## Consequences

- Clients see camelCase as the primary field spelling, except `call_id`.
- Schema-invalid tool calls fail as Action failures and do not reach handlers.
- Prompt context and persisted checkpoint data have explicit size/privacy
  bounds.
- Internal tool budgets measure work executed by this engine, not caller work.

## See also

- [D-020: `operation` is mandatory on every tool](./D-020-uniform-operation-field.md)
