# D-008: Base64-Inline Media Contract

- **Status:** Accepted
- **Owner:** Orchestrator
- **Related:** [Orchestrator Runtime](../architecture/orchestrator-runtime.md), [Wire Contract](../references/wire-contract.md), [D-007](./D-007-ordered-content-and-events.md)

## Context

Media URLs are mutable references that can expose internal addresses or become
unavailable after a response. Input and output media need bounded, verifiable
payloads that do not leak URL references through the unified contract.

## Decision

Media must be base64-inline after it enters the orchestration pipeline.
Incoming attachments are base64-only; callers fetch their own URLs before
submitting an attachment. Tool/provider media references are converted to
bounded inline bytes before response serialization. URL conversion requires
HTTPS, a configured hostname allowlist, and a public DNS address. Decoded
media is limited by `FORGE_MEDIA_MAX_BYTES` (default 20 MiB), and recognized
file signatures are checked against declared MIME types. The unified response
contains media only as typed `content` blocks; source citation URLs remain
separate.

For image analysis, the engine passes normalized base64 image data to a
configured `vision` dispatcher via
`analyze_image(prompt=..., system_prompt=..., images=...)`. The image list
contains only file ID/name, MIME type, and base64 bytes. Inline attachment
data is transient execution state and is excluded from checkpoint exports. If
no multimodal vision dispatcher is configured, image-analysis execution fails
explicitly.

## Consequences

- Remote-media hosts must be configured in `FORGE_MEDIA_ALLOWED_HOSTS`.
- Unapproved, non-HTTPS, non-public, mismatched-MIME, and oversized media URLs
  are rejected without passing their URL downstream.
- Responses remain self-contained and cannot expose media URLs.
- Deployments that convert remote media must explicitly configure allowed
  hosts; local files remain constrained by sandbox path policy.
