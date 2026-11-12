# D-005: Training Export Is Per-Request and Responses-Only

- **Status:** Accepted
- **Date:** 2026-11-09
- **Owner:** Orchestrator
- **Related:** [Orchestrator Runtime](../architecture/orchestrator-runtime.md), [D-004](./D-004-external-tools-two-phase-resume.md)

## Context

Training JSONL export is an optional observability side channel. The
Chat Completions endpoint was a provider passthrough when this decision was
written; it is now served by the registered Forge Text model. `/v1/responses`
remains the orchestrator-owned prompt-to-synthesis flow. Exporting every
request when the server toggle is enabled would collect data without an
explicit request from the caller.

## Decision

Export only when both `FORGE_TRAINING_EXPORT_ENABLED=true` and the individual
`/v1/responses` request sets `metadata.trainingExport=true`. The Forge-backed Chat
Completions route never calls the exporter. If export is requested while
disabled server-side, reject the request rather than silently ignoring it.

Compute effort is selected using `reasoning.effort`; execution topology is
derived internally from the presence of caller-owned tools. Training export
is rejected for interactive runs because no complete prompt-to-final-response
pair exists until a later request.

Only successful completed autonomous Responses runs are exported. The
orchestrator writes caller-visible prompt/response pairs in OpenAI JSONL
format, does not curate them, and keeps export off by default. Optional
Hugging Face synchronization is one-way; local files remain the source of
truth and upload failure does not fail a run.

## Consequences

- Server operators and callers must both opt in.
- Chat Completions request/response data is not collected by this feature.
- Interactive tool runs are not training examples.
- Retention and curation belong to the owning data/ML platform.

## Alternatives considered

- Export all runs whenever the server toggle is enabled: rejected because it
  lacks per-request consent and includes non-opt-in Chat Completions traffic.
- Combine effort and topology into a single enum: rejected because they answer
  independent runtime questions.
- Stitch interactive requests into training examples: rejected because that
  would introduce curation and cross-request data-retention semantics.
- Bidirectional Hugging Face sync: rejected; remote data must not overwrite
  local exports.
