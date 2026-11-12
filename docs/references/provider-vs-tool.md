# Provider and Tool Boundary

A **tool** is a planner-callable handler such as `speak` or `transcribe`. It
validates public arguments, invokes an injected **provider dispatcher**, and
returns the stable tool result. A **provider** owns model loading, runtime
configuration, and inference.

The `src/core/models/adapters/` package is reserved for AI model dispatchers
and model-runtime integrations. Non-model integrations that serve one tool,
such as the Open-Meteo HTTP client, live inside that tool's definition module
(`src/tools/definitions/weather.py`); do not add a generic service adapter to
the model package.

Speech tools do not import `httpx`, read provider URLs or credentials, or
choose underlying model files. Forge's `VoiceDispatcher` and `SttDispatcher` wrap `HuggingFaceInference`,
which loads Piper and faster-whisper from local weights. Text, embeddings,
diffusion, and speech use runtimes declared by `ModelDefinition.runtime`.
The public audio endpoints may use
OpenAI-compatible paths and fields; they call the same tools and do not call
OpenAI.

Local model repositories are registered in
`src/core/models/registry.py`. The model cache, CPU runtime devices, and
faster-whisper compute type are fixed in `src/core/models/huggingface.py`;
they are not deployment environment settings. Replace a repository in the
registry when a Forge-trained model is ready. See
[D-012](../decisions/D-012-forge-runs-local-speech-models.md) and
[D-018](../decisions/D-018-forge-runs-models-locally.md).
