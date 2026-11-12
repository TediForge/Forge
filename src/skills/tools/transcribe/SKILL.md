---
name: transcribe
description: Use to transcribe supplied speech audio with Forge's local faster-whisper model; do not use for non-speech media or audio metadata.
category: tool
version: 1.0
---

# Transcribe

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `audio` | Transcribe supplied audio | `mediaData`, `mimeType` | implemented |

## When to use
- The user provides an audio recording and asks for its spoken words.
- A voice note needs to be converted into text.
- Segment timings or a language hint are useful for the requested transcript.

## When not to use
- The input is text, not audio: use `summarize` or no tool.
- The audio is music or sound effects rather than speech: transcription may be empty or unreliable.
- The user asks about audio duration or codec: use `audio`.
- The input is a video: extract or provide its audio track first.

## How to call
`transcribe(operation="audio", mediaData, mimeType, language?, timestamps?, model?)`. `mediaData` is base64 audio. Audio must be at most 25 MB and use a supported audio format. `language` is an optional ISO-639-1 hint. Use the registry key `transcription`.

## Output
Returns `success`, `text`, and `language`; when timestamps are requested it also returns segment start/end times. Model/configuration failures are explicit.

## Examples
1. Transcribe a WAV voice note with `mimeType="audio/wav"`.
2. Pass `language="en"` when English is known and useful as a hint.
3. Set `timestamps=true` when segment timing is needed.
4. Use `model="transcription"`; its Hugging Face repository is defined in `src/core/models/registry.py`.
5. Transcribe an audio attachment after passing its base64 data and declared MIME type.
6. Do not call this for a text transcript; summarize the supplied text instead.
7. **Wrong operation:** An unsupported operation returns `INVALID_OPERATION`; use `audio`.

## Edge cases
- **Silence:** an empty transcript can be valid; do not fabricate words.
- **Music:** speech recognition may return empty or unreliable text.
- **Wrong MIME type:** unsupported media is rejected before inference; report the error.
- **Corrupt or empty data:** report the failure without retrying as another format.
- **Model unavailable:** surface the model error explicitly.
- **Over 25 MB:** reject before inference.
