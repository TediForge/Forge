# D-004: External Tools Use Two-Phase Resume

- **Status:** Accepted
- **Date:** 2026-11-09
- **Owner:** Orchestrator
- **Related:** [Orchestrator Runtime](../architecture/orchestrator-runtime.md), [D-001](./D-001-thoughts-at-action-site.md), [D-002](./D-002-separate-thoughts-from-actions.md)

## Context

The engine previously executed only tools with registered internal handlers.
Caller-supplied external functions need a way to be planned without giving the
orchestrator a handler or holding an HTTP request open while the caller runs
the function.

## Decision

External tools are schemas only. The planner may select one, at which point
the engine writes an atomic `suspended` checkpoint and returns a
`function_call` with a unique `call_id`. The caller executes the function and
resumes through `previous_response_id` plus a matching
`function_call_output` item inside `messages`. Public tool schemas are supplied
in the request's `tools` list. Internal registry tools execute in-process and
use their handler-owned Action descriptors.

The engine checks internal names first and rejects external names that collide
with internal tools. A `call_id` is the only resume correlation key. Resume
results are checkpointed and replayed for duplicate submissions.

Checkpoint containment and atomic replacement are prerequisites for this
feature. Checkpoint paths are constrained to the configured root and tenant
directory, and writes use a same-directory temporary file followed by atomic
replacement. Production deployments must configure `FORGE_CHECKPOINT_ROOT`
on persistent storage; a local file path cannot survive loss of its host or
ephemeral container volume.

The Responses HTTP surface accepts only an authenticated `Principal` supplied
by trusted upstream middleware. It does not trust caller-provided identity
fields or headers.

## Consequences

- No connection is held while a caller runs an external function.
- Suspended runs survive process restarts when checkpoint storage is mounted
  persistently.
- The caller owns all external function execution and result generation.
- Checkpoint files contain execution state and may contain sensitive
  arguments; deployment retention, access control, and encryption remain
  operational responsibilities.

## Alternatives considered

- Wait for a callback or hold the request open: rejected because execution
  duration is caller-controlled and creates a blocking connection.
- Invoke a caller-supplied callback URL: rejected because it would make the
  orchestrator perform outbound requests to caller-controlled destinations.
- Keep suspended runs only in memory: rejected because process restarts would
  make valid `call_id` values impossible to resume.
