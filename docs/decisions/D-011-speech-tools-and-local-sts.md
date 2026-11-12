# D-011: Separate Speech Tools and Push-to-Talk STS

- **Status:** Accepted (superseded by [D-012](./D-012-forge-runs-local-speech-models.md))
- **Date:** 2026-11-11
- **Owner:** Orchestrator
- **Related:** [D-009: One-word tool contract](./D-009-one-word-tool-contract.md), [Wire contract](../references/wire-contract.md)

## Context

Speech recognition and speech generation have different inputs, outputs, and
failure modes. Live speech also needs a stateful transport, but should not
duplicate orchestration or provider behavior.

## Decision

Register separate `transcribe` and `speak` tools. They call the OpenAI-compatible
`/v1/audio/transcriptions` and `/v1/audio/speech` endpoints, configured by
`FORGE_OPENAI_BASE_URL` and `FORGE_OPENAI_API_KEY`. The authenticated batch
HTTP endpoints and STS WebSocket reuse these same registered handlers.

`/v1/audio/sts` is an authenticated push-to-talk WebSocket that buffers client
PCM16 audio, converts it to WAV for transcription, passes the transcript to
`ForgeEngine.run`, then sends PCM speech output in chunks. It does not connect
to a Realtime provider and does not implement VAD in v1. The client controls
turn boundaries with `audio.commit`; `response.cancel` cancels the in-flight
turn.

## Consequences

- `audio` remains a metadata-probe tool; it does not perform STT or TTS.
- The STT and TTS tool schemas and skills remain independent.
- Provider keys are deployment configuration and must never be logged.
- The WebSocket's buffering and cancellation state is session-scoped.
- Server-side VAD, partial transcripts, and true streamed synthesis are
  follow-up capabilities, not v1 guarantees.

## See also

- [D-020: `operation` is mandatory on every tool](./D-020-uniform-operation-field.md)
