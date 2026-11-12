"""Local Piper speech synthesis backend."""

from orchestrator.inference.backends.transformers import TransformersBackend


class PiperBackend(TransformersBackend):
    backend_id = "piper"
    modalities = frozenset({"speech"})
