# D-025: Use One Reasoning Control and Opt-In Trajectory Export

- **Status:** Accepted
- **Date:** 2026-11-12
- **Owner:** Orchestrator
- **Related:** [D-005](./D-005-training-export-scope.md), [D-024](./D-024-multisource-inference-gateway.md)

## Context

The public Responses contract had two overlapping concepts for compute
selection and global input/output schema modules. Its optional data export
was named and shaped as a training dump rather than a bounded evaluation
handoff.

## Decision

`reasoning.effort` is the only request-facing reasoning-effort control.
Responses request and response models live together in
`schemas/v1/responses/models.py`; shared schema primitives live under
`schemas/common/`. Follow-up suggestions are an optional, opt-in field on the
final response and are empty for non-completed responses or when generation
is unavailable.

Trajectory export remains opt-in at both server and request levels. JSONL
records are schema-versioned, purpose-bound, bounded in size, redacted for
common credentials, emails, and phone numbers, and written outside the live
response path. Export is for evaluation and future curation; it is not an
automatic training service.

## Consequences

- Clients do not need to coordinate separate execution-mode and reasoning
  effort values.
- Route-specific API contracts can evolve independently.
- Exported rows have a documented shape and explicit consumer; exports remain
  disabled by default.
