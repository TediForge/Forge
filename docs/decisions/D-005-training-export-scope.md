# D-005: Trajectory Export Is Opt-In and Responses-Only

> **Partially superseded by [D-025](./D-025-response-effort-suggestions-trajectories.md):** the
> former training-export terminology and prompt/response-only format are
> superseded by a bounded, versioned, redacted trajectory contract. The
> explicit-consent and completed autonomous-run boundary remains in force.
> **The server-side environment gate is superseded by [D-027](./D-027-deployment-configuration-boundary.md).**

- **Status:** Accepted
- **Date:** 2026-11-09
- **Owner:** Orchestrator
- **Related:** [Orchestrator Runtime](../architecture/orchestrator-runtime.md), [D-004](./D-004-external-tools-two-phase-resume.md)

## Context

Trajectory JSONL export is an optional evaluation side channel. The
Chat Completions endpoint was a provider passthrough when this decision was
written; it is now served by the registered Forge Text model. `/v1/responses`
remains the orchestrator-owned prompt-to-synthesis flow. Exporting every
request would collect data without explicit consent from the caller.

## Decision

Export only when the individual `/v1/responses` request sets
`trajectoryExport=true`. The Forge-backed Chat Completions route never calls
the exporter. Export requires explicit request consent and is not activated
by deployment configuration.

Compute effort is selected using `reasoning.effort`; execution topology is
derived internally from the presence of caller-owned tools. Training export
is rejected for interactive runs because no complete prompt-to-final-response
pair exists until a later request.

Only successful completed autonomous Responses runs are exported. Records
include a schema version, purpose, run identifier, messages, steps, tool calls,
outcome, and metadata. Common credentials, emails, and phone numbers are
redacted, and records exceeding the configured size limit are dropped.
Export is inactive unless requested. Optional Hugging Face synchronization is
one-way and requires a configured repository ID and `HF_TOKEN` with write
permission; local files remain the source of truth and upload failure does not
fail a run. This data handoff does not train a model.

## Consequences

- Callers must explicitly opt in on each eligible request.
- Chat Completions request/response data is not collected by this feature.
- Interactive tool runs are not training examples.
- Retention and curation belong to the owning data/ML platform.

## Alternatives considered

- Export all runs: rejected because it lacks per-request consent and includes
  non-opt-in Chat Completions traffic.
- Combine effort and topology into a single enum: rejected because they answer
  independent runtime questions.
- Stitch interactive requests into training examples: rejected because that
  would introduce curation and cross-request data-retention semantics.
- Bidirectional Hugging Face sync: rejected; remote data must not overwrite
  local exports.
