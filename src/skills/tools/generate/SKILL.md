---
name: generate
description: Use to generate images with Forge Canvas or speech audio with Forge Voice; do not use for video generation or analysis.
category: tool
---

# Generate

## Operations

| `operation` | What it does | Required args | Status |
|---|---|---|---|
| `image` | Generate a local image | `prompt`, `output_path` | implemented |
| `audio` | Generate speech from a prompt | `prompt` | implemented |

## When to use
- The user explicitly asks for a generated image or spoken audio.
- A new sandbox output path is available for image generation.
- The Forge model provider is configured for the requested modality.

## When not to use
- Do not use for video; video generation is not registered.
- Do not use for image analysis or audio transcription.
- Do not use to claim completion when a local provider is unavailable.

## How to call
Call `generate(operation="image", prompt, output_path)` or `generate(operation="audio", prompt)`. Both use local Forge models; image output is saved in the sandbox.

## Examples
1. Image: `generate(operation="image", prompt="A cabin in snow", output_path="outputs/cabin.png")`.
2. Audio: `generate(operation="audio", prompt="Welcome to the event.")`.
3. For speech from exact supplied text, use `speak(operation="text")`.
4. If the local model is not configured, report `PROVIDER_NOT_CONFIGURED`.
5. Wrong operation returns `INVALID_OPERATION`; video is not exposed.
6. Do not claim an output path or media asset unless returned.

## Edge cases
- **Provider missing:** report `PROVIDER_NOT_CONFIGURED`.
- **Unknown operation:** report `INVALID_OPERATION`.
- **Existing output path:** report `OUTPUT_EXISTS`; choose another name.
- **Image result shape:** report `INVALID_PROVIDER_RESULT` if no supported image was returned.
- **Audio model error:** report `GENERATION_FAILED`; do not claim speech was produced.
- **Adjacent speech:** text-to-speech is not general audio generation.
