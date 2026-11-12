"""Multi-source, multi-backend inference entry point."""

from .gateway import InferenceGateway
from .protocols import InferenceRequest, InferenceResponse

__all__ = ["InferenceGateway", "InferenceRequest", "InferenceResponse"]
