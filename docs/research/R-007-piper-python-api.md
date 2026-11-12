# R-007: Piper Python API

- **Date checked:** 2026-11-11
- **Purpose:** Verify the local TTS runtime selected for Forge.

## Findings

Piper's Python API documents installing `piper-tts`, loading a local ONNX
voice model with `PiperVoice.load`, and synthesizing WAV output. The API also
supports synthesis settings such as `length_scale`; raw streaming audio chunks
are available through `synthesize`.

## Sources

- [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
- [Piper package](https://pypi.org/project/piper-tts/)

## Caveats

The library API does not guarantee every output codec exposed by other speech
services. Forge therefore exposes only WAV and PCM in the current local tool.
