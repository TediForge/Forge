"""Local Diffusers image and video generation backend."""

from orchestrator.inference.backends.transformers import TransformersBackend


class DiffusersBackend(TransformersBackend):
    backend_id = "diffusers"
    modalities = frozenset({"image_gen", "video"})
