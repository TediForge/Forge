# D-027: Deployment Configuration Is Separate from Code Defaults

- **Status:** Accepted
- **Date:** 2026-11-12
- **Owner:** Orchestrator
- **Related:** [D-005](./D-005-training-export-scope.md), [D-008](./D-008-base64-inline-media.md), [D-025](./D-025-response-effort-suggestions-trajectories.md)

## Context

The committed environment template had accumulated fixed safety limits,
default directories, and behavior toggles alongside secrets and deployment
values. This duplicated code defaults and made behavior depend on environment
variables that were not obvious from the request or service contract.

## Decision

Environment configuration is reserved for values that legitimately vary by
deployment: deployment identity, secret credentials, mounted paths, model
device selection, external endpoints, and deployment-specific allowlists.
Stable application defaults, safety limits, and request choices belong in
code or the request contract, not in `.env.example`.

- Attachment and media size limits are code-owned constants.
- Trajectory export is enabled by explicit request consent on a completed
  autonomous Responses run; no server environment toggle is required.
- Optional Hugging Face upload requires a destination repository ID and
  `HF_TOKEN` with write permission. The token can also authorize private model
  downloads; the repository type is fixed to `dataset`.
- Checkpoint, sandbox, model-cache, and audit paths retain optional deployment
  overrides, but default paths are not repeated in `.env.example` unless the
  deployment must supply or mount them.
- `.env.example` lists supported deployment values with safe defaults or
  commented placeholders. Secrets are blank placeholders and are never
  committed with live values.

## Consequences

- Deployments cannot weaken request/media size limits through environment
  configuration.
- Export requires per-request consent and successful autonomous completion;
  Hub upload requires an explicit destination and secret.
- Changing safety limits or export policy requires a reviewed code change.
- Supported path overrides remain available to deployments without making
  repository defaults appear mandatory.

## Supersession

This decision supersedes the server-side `FORGE_TRAJECTORY_EXPORT_ENABLED`
gate in D-005 and the environment-configurable media limit in D-008. The
explicit per-request consent, completed autonomous-run restriction,
redaction, bounded record size, and one-way upload semantics remain in force.
