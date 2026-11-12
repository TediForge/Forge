# D-018: Forge Runs Models Locally

- **Status:** Accepted
- **Date:** 2026-11-11
- **Owner:** Orchestrator
- **Related:** [D-012: Forge runs local speech models](./D-012-forge-runs-local-speech-models.md), [Provider/tool boundary](../references/provider-vs-tool.md)

## Context

The Hugging Face model registry identifies model repositories. Posting
inference requests to a hosted Hugging Face endpoint makes the orchestrator a
third-party inference client and ignores configured local hardware and model
parameters.

## Decision

Hugging Face Hub is a model-weight source, not an inference provider.
`HuggingFaceSource` resolves a configured model locator, then a backend loads
the resolved local artifact and performs inference on the deployed machine.
The Hub token is optional and is used only to download private model weights.

Runtime selection is explicit. Text generation uses Transformers, diffusion
uses Diffusers, embeddings use Sentence Transformers, transcription uses
faster-whisper, and speech synthesis uses Piper. Registry parameters are
merged with request options and passed to the relevant local runtime. The
orchestrator does not POST to Hugging Face, OpenAI, Anthropic, or Google
inference endpoints.

## Consequences

- `HF_TOKEN` is a model-download credential, not an inference credential.
- Default artifact locators are selected in
  `src/orchestrator/inference/registry.py`; source configuration can override
  them when adopting a local or privately stored model artifact.
- Model cache, CPU devices, and transcription compute type are fixed in the
  local runtime source, not deployment environment variables.
- Model loading is lazy and cached for the application lifetime.
- First use may require network access to download model weights; subsequent
  inference uses the local snapshot.
- Unsupported or invalid local runtime configuration fails explicitly.
