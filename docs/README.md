# Forge Orchestrator Documentation

This folder owns implementation documentation for the Forge orchestrator.
The core backend has a separate documentation surface at
[`../core/docs/`](../../core/docs/README.md).

## Structure and conventions

```text
docs/
├── README.md
├── architecture/
├── guides/
├── references/
├── decisions/
└── research/
```

Use three-digit `D-XXX-title-in-kebab-case.md` and
`R-XXX-title-in-kebab-case.md` filenames for decisions and research. Check the
highest number before creating a document. Accepted decisions are immutable;
supersede them with a new decision.

Do not create placeholder decisions to fill a numbering range. Record only
decisions supported by an explicit architectural choice, and link research
records to the primary sources actually checked. Research is evidence, not an
implementation contract; update the decision if the choice changes. Every
superseded accepted decision must have a "Partially superseded by D-XXX" block
at the top pointing to its replacement.

### Architecture (`architecture/`)

Keep complete explanations of how the orchestrator works here, including
system flows and deep-dives. Use unnumbered kebab-case filenames, one topic
per file, and update them when behavior changes. Link related decisions as
`See D-XXX`.

The single current end-to-end explanation is
[Orchestrator Runtime](./architecture/orchestrator-runtime.md).

### Guides and references

Guides are step-by-step procedures. References are stable lookups such as API
contracts and Thought/Action IDs. Keep one topic per file, date decisions and
research, link instead of duplicating, and do not delete decision or research
history.

## Existing references

- [OpenAPI document](./openapi.json)
- [Thought and Action contract](./references/thought-contract.md)
- [Public wire contract](./references/wire-contract.md)
- [Skill taxonomy and quality standard](./references/skills.md)
- [Caller-owned external tools](./references/external-tools.md)
- [Provider/tool boundary](./references/provider-vs-tool.md)
- [Thought IDs](./references/thought-ids.md)
- [Action IDs](./references/action-ids.md)
- [Optional trajectory export implementation](../src/orchestrator/export/)

## Decisions

- [D-001: Thoughts and Actions own IDs at their emission sites](./decisions/D-001-thoughts-at-action-site.md)
- [D-002: Separate Thoughts from Actions](./decisions/D-002-separate-thoughts-from-actions.md)
- [D-003: Remove unwired policy scaffolding](./decisions/D-003-remove-unwired-policy-scaffolding.md)
- [D-004: External tools use two-phase resume](./decisions/D-004-external-tools-two-phase-resume.md)
- [D-005: Trajectory export is opt-in and Responses-only](./decisions/D-005-training-export-scope.md)
- [D-006: CamelCase wire contract and central tool validation](./decisions/D-006-wire-camelcase-and-validation.md)
- [D-007: Ordered content blocks and event timeline](./decisions/D-007-ordered-content-and-events.md)
- [D-008: Base64-inline media contract](./decisions/D-008-base64-inline-media.md)
- [D-009: One-word tool names and mandatory tool skills](./decisions/D-009-one-word-tool-contract.md)
- [D-010: Orchestrator owns no service integrations](./decisions/D-010-orchestrator-owns-no-service-integrations.md)
- [D-011: Separate speech tools and push-to-talk STS](./decisions/D-011-speech-tools-and-local-sts.md)
- [D-012: Forge runs local speech models](./decisions/D-012-forge-runs-local-speech-models.md)
- [D-013: Title generation is client-owned](./decisions/D-013-title-generation-is-client-owned.md)
- [D-018: Forge runs models locally](./decisions/D-018-forge-runs-models-locally.md)
- [D-019: One tool per domain, operations inside the tool, one skill per tool](./decisions/D-019-one-tool-per-domain-one-skill.md)
- [D-020: `operation` is mandatory on every tool](./decisions/D-020-uniform-operation-field.md)
- [D-021: No registered placeholder operations](./decisions/D-021-no-registered-placeholder-operations.md)
- [D-022: No stateful tools](./decisions/D-022-no-stateful-tools.md)
- [D-023: Keep non-model integrations in their tool modules](./decisions/D-023-tool-local-non-model-integrations.md)
- [D-024: Inference is multi-backend and multi-source](./decisions/D-024-multisource-inference-gateway.md)
- [D-025: One reasoning control, optional suggestions, and bounded trajectories](./decisions/D-025-response-effort-suggestions-trajectories.md)

## Research

- [R-001: OpenAI-compatible audio shapes](./research/R-001-openai-audio-shapes.md)
- [R-002: OpenAI Responses API shape](./research/R-002-openai-responses-shape.md)
- [R-003: Anthropic Messages API](./research/R-003-anthropic-messages-api.md)
- [R-004: Gemini content generation](./research/R-004-gemini-content-generation.md)
- [R-005: xAI Responses API](./research/R-005-xai-responses-api.md)
- [R-006: faster-whisper](./research/R-006-faster-whisper.md)
- [R-007: Piper Python API](./research/R-007-piper-python-api.md)
