# D-012: Forge Runs Local Speech Models

- **Status:** Accepted
- **Date:** 2026-11-11
- **Owner:** Orchestrator
- **Supersedes:** The provider selection in [D-011](./D-011-speech-tools-and-local-sts.md)
- **Related:** [D-010: Orchestrator owns no service integrations](./D-010-orchestrator-owns-no-service-integrations.md), [R-001: OpenAI-compatible audio shapes](../research/R-001-openai-audio-shapes.md), [R-006: faster-whisper](../research/R-006-faster-whisper.md), [R-007: Piper](../research/R-007-piper-python-api.md)

## Context

D-011 established separate speech tools and a push-to-talk session, but its
provider choice incorrectly made the orchestrator an HTTP client of an
OpenAI-compatible speech service. The orchestrator owns model execution and
must not use OpenAI credentials or outbound provider calls for speech.

## Decision

The orchestrator uses local faster-whisper for STT and Piper for TTS. The
`transcribe` and `speak` handlers call injected Forge dispatchers; only the
dispatcher knows model loading and runtime configuration. The public audio
routes may follow OpenAI-compatible paths and request shapes, but these are
wire compatibility only. They are not instructions to call OpenAI.

The Piper integration advertises only its registry-selected default voice and
WAV or raw PCM output. The faster-whisper integration uses the `transcription`
registry key. Speech model repositories, CPU devices, cache, and compute type
are source-controlled defaults; replacing a repository in the model registry
is the intended way to adopt a Forge-trained model. No `FORGE_OPENAI_*`
variables or external speech service credentials are used.

## Consequences

- The `audio` and `transcription` entries in
  `src/core/models/registry.py` select the local model repositories.
- Runtime cache, device, and compute settings are constants in
  `src/core/models/huggingface.py`.
- `/v1/audio/transcriptions`, `/v1/audio/speech`, and `/v1/audio/sts` reuse
  the same local tool handlers and injected dispatchers.
- Unsupported Piper output formats or speech instructions are rejected
  explicitly rather than silently converted or ignored.
- [D-011](./D-011-speech-tools-and-local-sts.md) remains as immutable history;
  this record supersedes its provider choice.

## See also

- [D-020: `operation` is mandatory on every tool](./D-020-uniform-operation-field.md)
