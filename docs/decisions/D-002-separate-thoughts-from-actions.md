# D-002: Separate Thoughts from Actions

- **Status:** Accepted
- **Date:** 2026-11-09
- **Owner:** Orchestrator
- **Related:** [Thought and Action Contract](../references/thought-contract.md), [Thought IDs](../references/thought-ids.md), [Action IDs](../references/action-ids.md), [D-001](./D-001-thoughts-at-action-site.md)

## Context

Tool execution was represented as `thought` events. This conflated user-visible
progress with execution facts and offered no structured action lifecycle.

## Decision

Thoughts describe user-safe reasoning or progress intent. Tool, integration,
data, and attachment operations use a separate `action` event with a stable
`A`-prefixed ID and `started` → `processing` → `completed` or `failed`
lifecycle. Run lifecycle is represented by a `status` event. Stream envelopes
also include `textChunk` and terminal `complete`.

Static responses expose `thoughts` and `actions` separately. During one
compatibility release, tool actions may additionally emit a legacy Thought
marked `data.deprecated: true`; after that window clients should consume
Action events only. Action metadata is redacted and does not include raw
arguments, results, or exceptions.

## Consequences

- Clients can render reasoning, execution, and run state independently.
- Action IDs replace tool-specific entries in the Thought ID catalog.
- Existing consumers of tool Thoughts must migrate during the compatibility
  release.
- Status/action event schemas and redaction behavior are covered by tests.

## Alternatives considered

- Keep tool activity in Thoughts: rejected because event type would continue
  to conflate intent and execution.
- Infer action cards from Thought `data`: rejected because it leaves clients
  dependent on heuristic payload inspection.
- Add telemetry spans as a substitute: rejected; telemetry is not a
  user-facing Action event and is out of scope.
