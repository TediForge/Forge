"""Typed model catalog for the orchestrator."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping


ModelRuntime = Literal[
    "transformers",
    "vision-transformers",
    "diffusers",
    "sentence-transformers",
    "faster-whisper",
    "tts",
]


@dataclass(frozen=True)
class ModelDefinition:
    model_id: str
    hf_repo: str
    runtime: ModelRuntime
    description: str
    capabilities: tuple[str, ...]
    parameters: Mapping[str, object]
    supports_tools: bool
    supports_streaming: bool
    allow_patterns: tuple[str, ...] | None = None


def _model(
    model_id: str,
    hf_repo: str,
    runtime: ModelRuntime,
    description: str,
    capabilities: tuple[str, ...],
    parameters: dict[str, object],
    supports_tools: bool,
    supports_streaming: bool,
    allow_patterns: tuple[str, ...] | None = None,
) -> ModelDefinition:
    return ModelDefinition(
        model_id=model_id,
        hf_repo=hf_repo,
        runtime=runtime,
        description=description,
        capabilities=capabilities,
        parameters=MappingProxyType(parameters),
        supports_tools=supports_tools,
        supports_streaming=supports_streaming,
        allow_patterns=allow_patterns,
    )


MODELS: Mapping[str, ModelDefinition] = MappingProxyType({
    "text": _model(
        "Text", "Qwen/Qwen2.5-0.5B-Instruct", "transformers",
        "Primary multilingual LLM for chat, reasoning, and code",
        ("chat", "reasoning", "code", "toolUse"),
        {"temperature": 0.7, "topP": 0.9, "maxTokens": 4096}, True, True,
    ),
    "image": _model(
        "Canvas", "stabilityai/sd-turbo", "diffusers",
        "Visual diffusion engine for image generation and editing",
        ("textToImage", "imageEditing"),
        {"num_inference_steps": 1, "guidance_scale": 0.0}, False, False,
    ),
    "audio": _model(
        "Voice", "rhasspy/piper-voices", "tts",
        "Local Piper speech synthesis model",
        ("textToSpeech",),
        {"defaultVoice": "en_US-lessac-medium", "sampleRate": 22050}, False, True,
        (
            "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
            "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        ),
    ),
    "transcription": _model(
        "Speech", "Systran/faster-whisper-small", "faster-whisper",
        "Local faster-whisper speech transcription model",
        ("speechToText",),
        {}, False, False,
    ),
    "video": _model(
        "Motion", "zai-org/CogVideoX-2b", "diffusers",
        "Video generation, animation, and timeline composition model",
        ("textToVideo", "videoEditing", "keyframeGeneration", "frameInterpolation", "videoComposition"),
        {
            "num_frames": 49,
            "height": 480,
            "width": 720,
            "num_inference_steps": 50,
            "guidance_scale": 6.0,
        }, True, True,
    ),
    "vision": _model(
        "Vision", "HuggingFaceTB/SmolVLM-256M-Instruct", "vision-transformers",
        "Multimodal perception for image and video understanding",
        ("imageAnalysis", "videoUnderstanding", "keyframeSampling", "objectDetection", "ocr", "spatialExtraction", "visualReasoning"),
        {"temperature": 0.2, "maxTokens": 2048}, True, True,
    ),
    "document": _model(
        "Ledger", "Qwen/Qwen2.5-0.5B-Instruct", "transformers",
        "Document extraction, invoice processing, table parsing, and structured retrieval",
        ("pdfParsing", "invoiceExtraction", "tableExtraction", "documentOcr", "structuredRag"),
        {"temperature": 0.1, "maxTokens": 4096}, True, False,
    ),
    "data": _model(
        "Analyst", "Qwen/Qwen2.5-Coder-0.5B-Instruct", "transformers",
        "Data analysis, SQL generation, statistical reasoning, visualization, and reporting",
        ("sqlGeneration", "pandasSandbox", "datasetProfiling", "dataJoin", "chartGeneration", "reportCompilation", "warehouseQuery"),
        {"temperature": 0.1, "maxTokens": 8192, "readOnlyDefault": True}, True, True,
    ),
    "embedding": _model(
        "Embed", "sentence-transformers/all-MiniLM-L6-v2", "sentence-transformers",
        "Vector embedding model for semantic search and memory lookup",
        ("textEmbedding",),
        {"dimensions": 384, "maxInputTokens": 256}, False, False,
    ),
})


def get_model(key: str) -> ModelDefinition:
    """Resolve a model by registry key, model ID, or Hugging Face repository."""
    normalized_key = key.casefold()
    for registry_key, definition in MODELS.items():
        if normalized_key in {
            registry_key.casefold(),
            definition.model_id.casefold(),
            definition.hf_repo.casefold(),
        }:
            return definition
    raise KeyError(f"Unknown model: {key}")
