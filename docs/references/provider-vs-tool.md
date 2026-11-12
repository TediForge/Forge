# Provider and Tool Boundary

A **tool** is a planner-callable handler such as `speak` or `transcribe`. It
validates public arguments, invokes an injected **provider dispatcher**, and
returns the stable tool result. A **provider** owns model loading, runtime
configuration, and inference.

The `src/orchestrator/inference/` package owns model registries, artifact
sources, inference backends, and modality dispatchers. The old
`src/orchestrator/models/` compatibility package was removed during the
migration; there are no legacy model imports to retain. Non-model integrations
that serve one tool, such as the Open-Meteo HTTP client, live inside that
tool's definition module (`src/orchestrator/tools/definitions/weather.py`);
do not add a generic service adapter to the inference subsystem.

Speech tools do not import `httpx`, read provider URLs or credentials, or
choose underlying model files. Forge's `VoiceDispatcher` and `SttDispatcher`
call providers exposed by `InferenceGateway`; Piper and faster-whisper are
backends that run on source-resolved weights.
The public audio endpoints may use
OpenAI-compatible paths and fields; they call the same tools and do not call
OpenAI.

Local model repositories and capabilities are registered in
`src/orchestrator/inference/registry.py`. Source and backend configuration is
centralized in inference settings. See
[D-012](../decisions/D-012-forge-runs-local-speech-models.md) and
[D-018](../decisions/D-018-forge-runs-models-locally.md).
