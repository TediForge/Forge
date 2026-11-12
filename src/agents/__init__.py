"""Collaborative specialist agents for Forge."""

from .base import AgentMessage, BaseAgent
from .coding.agent import CodingAgent
from .data.agent import DataAgent
from .document.agent import DocumentAgent
from .media.agent import MediaAgent
from .registry import AgentRegistry
from .research.agent import ResearchAgent
from .vision.agent import VisionAgent


def create_default_agents(dispatcher=None, vision_dispatcher=None) -> list[BaseAgent]:
    return [
        ResearchAgent(dispatcher),
        CodingAgent(dispatcher),
        DocumentAgent(dispatcher),
        DataAgent(dispatcher),
        VisionAgent(vision_dispatcher if vision_dispatcher is not None else dispatcher),
        MediaAgent(dispatcher),
    ]


__all__ = [
    "AgentMessage",
    "BaseAgent",
    "AgentRegistry",
    "CodingAgent",
    "DataAgent",
    "DocumentAgent",
    "MediaAgent",
    "ResearchAgent",
    "VisionAgent",
    "create_default_agents",
]
