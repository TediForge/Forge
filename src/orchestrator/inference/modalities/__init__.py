"""Thin inference facades for engine and tools."""

from .embedding import EmbeddingFacade
from .imagegen import ImageGenFacade
from .canvas import CanvasDispatcher
from .base import BaseDispatcher, DispatcherError
from .stt import SttDispatcher
from .speech import SpeechFacade
from .text import TextFacade
from .textdispatch import TextDispatcher
from .transcription import TranscriptionFacade
from .vision import VisionFacade
from .voice import VoiceDispatcher

__all__ = [
    "BaseDispatcher", "CanvasDispatcher", "DispatcherError", "EmbeddingFacade",
    "ImageGenFacade", "SpeechFacade", "SttDispatcher", "TextDispatcher",
    "TextFacade", "TranscriptionFacade", "VisionFacade", "VoiceDispatcher",
]
