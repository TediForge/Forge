# R-006: faster-whisper

- **Date checked:** 2026-11-11
- **Purpose:** Verify the local STT runtime selected for Forge.

## Findings

The faster-whisper project describes a Whisper implementation built on
CTranslate2. Its documented Python interface loads a `WhisperModel` and
transcribes audio with options including language and word timestamps.

## Sources

- [faster-whisper project and usage](https://github.com/SYSTRAN/faster-whisper)
- [faster-whisper package](https://pypi.org/project/faster-whisper/)

## Caveats

This confirms the library interface, not model accuracy, hardware
compatibility, deployment performance, or model-file licensing. Those require
separate evaluation for the chosen model and deployment.
