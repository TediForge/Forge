# D-007: Ordered Content Blocks and Event Timeline

- **Status:** Accepted
- **Owner:** Orchestrator
- **Related:** [Orchestrator Runtime](../architecture/orchestrator-runtime.md), [D-002](./D-002-separate-thoughts-from-actions.md), [D-008](./D-008-base64-inline-media.md)

## Context

A text string plus a separate media array cannot preserve the position of
generated media relative to text. Separate top-level thought/action arrays
also lose their execution ordering.

## Decision

Unified responses use an ordered `content` array of typed text/media blocks
and one ordered `events` list for Thought, Action, and RunStatus records.
Clients render content blocks in array order and consume lifecycle events in
timeline order. There are no separate top-level `thoughts`, `actions`, or
`mediaAssets` fields in the unified response. Endpoint-specific formatters may
derive a legacy media index without changing this canonical shape.

## Consequences

- Text/media interleaving is explicit and stable.
- Response and stream completion share a single event timeline.
- Consumers must migrate from the removed top-level arrays.
