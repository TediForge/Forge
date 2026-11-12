"""Local faster-whisper transcription backend."""

from orchestrator.inference.backends.transformers import TransformersBackend


class WhisperBackend(TransformersBackend):
    backend_id = "whisper"
    modalities = frozenset({"transcription"})
