---
name: image
description: Use to inspect, resize, OCR, or generate sandboxed images; do not use for video or audio.
category: tool
version: 1.0
---

# Image

## When to use
- The user asks about image contents, text, objects, dimensions, format, or resizing.
- The user asks to generate an image from a prompt.
- The user asks to extract visible writing from an image.

## When not to use
- Video input: use `video`.
- PDF text extraction: use `pdf(operation="text")`.
- Audio metadata: use `audio`.
- Chart creation from data: use `data(operation="chart")`.
- Text-only tasks: do not call this tool.
- Do not use for video metadata or frames; use `video`.
- Do not use for audio transcription; use `transcribe`.

## Operations
`image(operation, ...)` with exactly one operation:

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `info` | Read format, dimensions, and color mode | `path` | implemented |
| `resize` | Save a resized copy | `path`, `output_path`, `width`, `height` | implemented |
| `ocr` | Extract visible text | `path` | implemented |
| `generate` | Generate and save an image | `prompt`, `output_path` | implemented |

## How to call
Call `image(operation=..., ...)` and provide the arguments shown for that operation.

## Output
Returns an operation-specific object with `success`, result fields, `error`, and `errorCode`. Reads and writes stay inside the sandbox workspace; generation requires the local Forge Canvas model.

## Examples
1. **Metadata:** `image(operation="info", path="photo.png")` for dimensions and format.
2. **Resize:** `image(operation="resize", path="photo.png", output_path="small.png", width=400, height=300)`.
3. **OCR:** `image(operation="ocr", path="uploads/receipt.png")` for visible text.
4. **Generate:** `image(operation="generate", prompt="A red kite over a field", output_path="outputs/kite.png")`.
5. **Unavailable analysis:** image analysis/detection are not registered; use only the listed operations.
6. **Wrong operation:** An unsupported operation returns `INVALID_OPERATION`.
7. **PDF boundary:** use `pdf` to extract PDF text.

## Edge cases
- **Missing file:** return `NOT_FOUND`; do not invent image content.
- **Path outside workspace:** return `PATH_NOT_ALLOWED`; do not retry an alternate path.
- **Corrupt or unsupported image:** report the file error rather than claiming metadata or OCR succeeded.
- **Blank OCR input:** return empty extracted text as a valid OCR result.
- **Generation provider absent:** report `PROVIDER_NOT_CONFIGURED`; do not claim an image exists.
- **Output already exists:** report `OUTPUT_EXISTS`; choose a new path.
- **OCR dependency unavailable:** surface the dependency error; do not invent text.
- **Invalid resize dimensions:** report `INVALID_DIMENSIONS`; do not overwrite the source.
- **Preserving proportions:** resize uses exact width and height; calculate proportional dimensions when aspect ratio must be preserved.
