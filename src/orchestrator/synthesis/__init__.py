"""Forge response synthesis."""

from .output import (
    OutputSynthesizer,
    SourceReference,
    StreamEvent,
    TerminalStatus,
    UnifiedOrchestratorResponse,
)
from .aggregator import AggregatedOutput, aggregate_output_items
from .errors import apply_failure_policy
from .formatter import to_chat_completion, to_responses
from .normalizer import normalize_media_assets, normalize_sources

__all__ = [
    "OutputSynthesizer",
    "SourceReference",
    "StreamEvent",
    "TerminalStatus",
    "UnifiedOrchestratorResponse",
    "AggregatedOutput",
    "aggregate_output_items",
    "apply_failure_policy",
    "normalize_media_assets",
    "normalize_sources",
    "to_chat_completion",
    "to_responses",
]
