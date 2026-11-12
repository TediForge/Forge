---
name: video
description: Use to inspect video properties or extract timestamped and scene-change frames; do not use for audio-only files or video generation.
category: tool
version: 1.0
---

# Video

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `probe` | Read video metadata using ffprobe | `path` | implemented |
| `sample` | Extract frames at requested timestamps | `path`, `timestamps`, `output_directory` | implemented |
| `keyframe` | Extract scene-change frames | `path`, `output_directory` | implemented |

## When to use
- The user asks about duration, format, size, bitrate, codec, dimensions, or frame rate.
- The user asks for individual frames or representative scene changes.
- The video is present inside the sandbox and the requested frame range is bounded.

## When not to use
- Audio-only file properties: use `audio`.
- Interpreting extracted frames: use an image-capable tool.
- Do not use for video generation; that operation is not registered.

## How to call
`video(operation, ...)` with the required arguments shown in the operations table. `keyframe` also accepts an optional `threshold`.

## Output
Metadata includes duration, format, size, bitrate, and video stream properties. Frame operations return paths under the sandbox outputs directory. Report missing executables and file errors explicitly.

## Examples
1. **Duration:** `video(operation="probe", path="clip.mp4")`.
2. **Codec:** use the `probe` stream details; do not infer codec from the file extension.
3. **Specific moments:** `video(operation="sample", path="clip.mp4", timestamps=[2.5, 8], output_directory="outputs/frames")`.
4. **Scene changes:** `video(operation="keyframe", path="clip.mp4", output_directory="outputs/keyframes")`.
5. **Interpretation:** extract frames first, then use an image-capable tool to describe them.
6. **Over-use boundary:** for an audio-only file, use `audio`, not `video`.
7. **Wrong operation:** An unsupported operation returns `INVALID_OPERATION`; choose `probe`, `sample`, or `keyframe`.

## Edge cases
- **Missing file:** report `NOT_FOUND`.
- **Missing `ffprobe` or `ffmpeg`:** report the explicit missing dependency error.
- **No video stream:** distinguish an empty stream list from a failed probe.
- **Invalid timestamps or threshold:** report the validation error and do not claim extraction succeeded.
- **Malformed metadata or timeout:** report the probe failure without unbounded retries.
