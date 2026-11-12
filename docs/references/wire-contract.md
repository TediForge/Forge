# Public Wire Contract

Public `/v1/responses` JSON fields use camelCase. Python implementation names
are internal and are mapped through `CamelBaseModel`'s `alias_generator` and
`populate_by_name` configuration. New public fields must be camelCase on the
wire.

The deliberate snake_case fields are `call_id` on function calls and
`previous_response_id` on resume requests.

The orchestrator request accepts caller-provided function schemas in `tools`,
execution effort in `reasoning.effort`, and resume results as
`function_call_output` items inside `messages`. It does not accept a client
session ID, topology, or separate function-output list. `trajectoryExport` is
an opt-in boolean that requests a redacted, versioned trajectory record when
server-side export is enabled. `includeSuggestions` opts in to optional
follow-up prompts; `suggestions` are returned only on the final completed
response and are empty when unavailable or inapplicable.

## Audio

Authenticated `POST /v1/audio/transcriptions` accepts multipart audio uploads
up to 25 MB and returns JSON (or plain text when requested). Authenticated
`POST /v1/audio/speech` accepts JSON and returns raw audio bytes. Both call the
same `transcribe` and `speak` handlers used by the tool registry. The paths
and request shapes are compatible with OpenAI audio clients, but inference is
local: `transcribe` uses faster-whisper and `speak` uses Piper. Forge makes no
OpenAI request and does not use `FORGE_OPENAI_*` settings. Speech currently
supports the configured Piper voice and WAV or raw PCM output.

Authenticated WebSocket `/v1/audio/sts` is a local push-to-talk session, not a
proxy or a Realtime-compatible endpoint. The client sends `session.start`,
base64 PCM16 `audio.input` chunks and `audio.commit`; the server invokes the
shared transcription handler, `ForgeEngine.run`, and shared speech handler.
`response.cancel` cancels the active turn. V1 does not perform server-side VAD.

Conversation titles are client-owned. There is no title-generation tool,
endpoint, request field, or response field in the orchestrator.

The unified response exposes ordered `content` blocks and one ordered
`events` timeline. Text and media are represented as typed content blocks;
media is base64-inline and does not expose a URL. See
[D-006](../decisions/D-006-wire-camelcase-and-validation.md),
[D-007](../decisions/D-007-ordered-content-and-events.md), and
[D-008](../decisions/D-008-base64-inline-media.md).

Input attachments are base64-only. `AttachmentPayload` has no URL field and
validates base64, decoded size, optional checksum, and declared MIME signatures
before processing. If the caller has a media URL, it must fetch the asset and
send the bytes as `fileData`. URLs returned by a tool as media references are
converted to base64 at the tool-result boundary, subject to HTTPS, public-DNS,
host-allowlist, MIME, and size checks. The original media URL is not passed to
vision or emitted in a media content block. Citation URLs remain valid in
`SourceReference.url`.

Inline image bytes are supplied to a configured `vision` dispatcher through
its `analyze_image` method. The method receives `prompt`, `system_prompt`, and
an `images` list containing `fileId`, `fileName`, `mimeType`, and base64
`mediaData`. These bytes are transient and excluded from checkpoint exports.
Without a multimodal vision dispatcher, image-analysis execution fails
explicitly rather than treating OCR text as visual analysis.
