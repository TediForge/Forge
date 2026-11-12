# R-001: OpenAI-Compatible Audio Shapes

- **Date checked:** 2026-11-11
- **Purpose:** Distinguish public audio wire compatibility from inference-provider ownership.

## Findings

OpenAI documents JSON requests for its speech operation and multipart uploads
for transcription. These documents can inform compatible request/response
shapes, but they describe OpenAI's own products and do not establish that
Forge should call those products.

## Sources

- [OpenAI text-to-speech guide](https://developers.openai.com/api/docs/guides/text-to-speech)
- [OpenAI speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text)
- [OpenAI voice agents guide](https://developers.openai.com/api/docs/guides/voice-agents)

## Application

Forge may expose compatible route shapes while running its own models. See
[D-012](../decisions/D-012-forge-runs-local-speech-models.md). This research
does not validate Forge model quality or provider behavior.
