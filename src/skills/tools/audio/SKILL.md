---
name: audio
description: Use to inspect, trim, or convert sandboxed audio files; do not use for transcription or speech generation.
category: tool
version: 1.0
---

# Audio

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `probe` | Inspect audio file metadata | `path` | implemented |
| `trim` | Trim an audio file | `path`, `output_path`, `start_seconds`, `duration_seconds` | implemented |
| `convert` | Convert an audio file | `path`, `output_path`, `output_format` | implemented |

## When to use
- The user asks about an audio file's properties or compatibility.
- You need duration or stream information before planning conversion or transcription.
- The user requests a bounded trim or conversion within the sandbox.

## When not to use
- Do not use to transcribe or generate speech.
- Do not use when the question is about audio content rather than file properties.
- Do not use for video processing; use `video`.

## How to call
`audio(operation, ...)`: use `probe(path)`, `trim(path, output_path, start_seconds, duration_seconds)`, or `convert(path, output_path, output_format)`. Processing requires `ffmpeg`; metadata inspection requires `ffprobe`.

## Output and edge cases
Returns `{success, path, durationSeconds, sizeBytes, formatName, bitRate, audioStreams, error, errorCode}`. `ffprobe` must be installed. Report missing files, unsupported media, or probe failures explicitly.

## Examples
1. **Probe:** `audio(operation="probe", path="uploads/voice.wav")` returns stream metadata.
2. **Trim:** `audio(operation="trim", path="uploads/voice.wav", output_path="outputs/clip.wav", start_seconds=4, duration_seconds=12)`.
3. **Convert:** `audio(operation="convert", path="uploads/voice.wav", output_path="outputs/voice.mp3", output_format="mp3")`.
4. **Transcription boundary:** For spoken words, use `transcribe`, not audio metadata.
5. **Wrong operation:** An unknown operation returns `INVALID_OPERATION`; select one of the three listed operations.
6. **Video boundary:** For video frame rate, use `video`.

## Edge cases
- **Missing path:** report `INVALID_PATH` or `NOT_FOUND`.
- **No ffprobe:** report `FFPROBE_MISSING`; do not claim a probe succeeded.
- **Probe timeout:** report `FFPROBE_TIMEOUT` without unbounded retries.
- **Audio stream absent:** report the returned empty stream list.
- **Metadata omitted:** preserve `null` values; do not guess codec or bitrate.
- **Invalid trim range:** report `INVALID_DURATION`; do not claim a file was created.
- **Output already exists:** report `OUTPUT_EXISTS`; choose a new output path.
- **Missing ffmpeg:** report `FFMPEG_MISSING`; no conversion occurred.
- **Processing timeout or codec error:** report the typed ffmpeg error; do not use partial output.
