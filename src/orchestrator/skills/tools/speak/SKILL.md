---
name: speak
description: Use to turn supplied text into spoken audio with Forge's local Piper model; do not use for music generation or transcription.
category: tool
version: 1.0
---

# Speak

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `text` | Generate speech from supplied text | `text` | implemented |

## When to use
- The user asks for a spoken version of text or an audio rendition of an answer.
- The spoken output should use the configured local Piper voice.
- The text fits within the model's supported request size.

## When not to use
- The user wants text only: do not call this tool.
- The user wants music or sound effects generated from a prompt: this speech tool is not appropriate.
- The user asks what an audio file contains: use `transcribe` for speech or `audio` for metadata.

## How to call
`speak(operation="text", text, voice?, format?, speed?, instructions?, model?)`. Text is limited to 4096 characters. Forge currently supports the configured `default` Piper voice, `wav` or raw `pcm` output, and speed from 0.25 to 4.0. Use model `forge-tts`.

## Output
Returns base64 `mediaData`, `mimeType`, and `fileSizeBytes`. The local Piper model and selected voice files are defined in `src/orchestrator/models/registry.py`. Model loading failures are explicit.

## Examples
1. Convert a short response to speech with `operation="text"` and the defaults.
2. Use `voice="default"` for the configured Piper voice.
3. Use `format="wav"` for a WAV container or `format="pcm"` for raw PCM.
4. Use `speed=1.25` for a moderately faster delivery.
5. Do not pass `instructions`; Piper does not support them.
6. For text longer than the limit, split at sentence boundaries and speak each chunk; do not silently truncate.
7. For music or sound effects, do not call `speak`.
8. **Wrong operation:** An unsupported operation returns `INVALID_OPERATION`; use `text`.

## Edge cases
- **Empty text:** reject it; do not generate silence.
- **Text over 4096 characters:** chunk at natural boundaries and preserve order.
- **Unsupported voice, speed, or format:** report the validation error.
- **Provider timeout/unavailable:** report the provider error explicitly.
- **Provider returns empty audio:** treat it as a failure, not a successful output.
