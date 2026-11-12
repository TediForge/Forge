"""Public response schemas for the Forge orchestrator."""

from enum import Enum
import base64
import os
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class TerminalStatus(str, Enum):
    COMPLETED = "completed"
    SUMMARIZED = "summarized"
    STOPPED_BUDGET = "stopped_budget"
    STOPPED_CIRCUIT_BREAKER = "stopped_circuit_breaker"
    FAILED = "failed"


TERMINAL_EVENTS = {status.value for status in TerminalStatus}


class CamelBaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class SourceReference(CamelBaseModel):
    title: str
    url: str
    snippet: Optional[str] = None
    sourceType: Literal["web", "document", "integration", "other"] = "other"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContentBlock(CamelBaseModel):
    """Ordered text or base64-inline media content."""

    type: Literal["text", "image", "video", "audio", "file"]
    text: Optional[str] = None
    assetId: Optional[str] = None
    mediaData: Optional[str] = Field(default=None, description="Base64-encoded bytes for non-text blocks")
    mimeType: Optional[str] = None
    fileName: Optional[str] = None
    fileSizeBytes: Optional[int] = Field(default=None, ge=0)
    altText: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_content_shape(self):
        if self.type == "text":
            if not self.text:
                raise ValueError("text block requires non-empty text")
            if self.mediaData is not None:
                raise ValueError("text block must not carry mediaData")
        else:
            if not self.mediaData:
                raise ValueError(f"{self.type} block requires mediaData")
            if not self.mimeType:
                raise ValueError(f"{self.type} block requires mimeType")
            try:
                raw = base64.b64decode(self.mediaData, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise ValueError("mediaData must be valid base64") from exc
            maxBytes = int(os.getenv("FORGE_MEDIA_MAX_BYTES", 20 * 1024 * 1024))
            if maxBytes < 1 or len(raw) > maxBytes:
                raise ValueError(f"decoded mediaData exceeds the {maxBytes}-byte limit")
            if self.fileSizeBytes is not None and self.fileSizeBytes != len(raw):
                raise ValueError("fileSizeBytes does not match mediaData")
        return self


class Thought(CamelBaseModel):
    id: str = Field(..., pattern="^T[A-Z0-9]{5}$")
    type: Literal["thought"] = "thought"
    message: str = Field(..., min_length=1)
    status: Literal["started", "processing", "completed"] = "processing"
    data: Dict[str, Any] = Field(default_factory=dict)


class ActionRecord(CamelBaseModel):
    type: Literal["action"] = "action"
    actionId: str = Field(..., pattern="^A[A-Z0-9]{5}$")
    actionType: Literal["tool", "integration", "data", "attachment"]
    toolName: Optional[str] = None
    status: Literal["started", "processing", "completed", "failed"]
    message: str = Field(..., min_length=1)
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, str]] = None


class RunStatus(CamelBaseModel):
    type: Literal["status"] = "status"
    status: Literal["started", "planned", "completed", "failed", "cancelled", "requires_action"]
    terminationReason: Optional[str] = None
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None
    stepCount: Optional[int] = None
    toolCallCount: Optional[int] = None


OrchestratorEvent = Annotated[
    Union[Thought, ActionRecord, RunStatus],
    Field(discriminator="type"),
]


class FunctionCall(CamelBaseModel):
    type: Literal["function_call"] = "function_call"
    call_id: str = Field(
        ...,
        alias="call_id",
        serialization_alias="call_id",
        validation_alias=AliasChoices("call_id", "callId"),
    )
    name: str
    arguments: str


class UnifiedOrchestratorResponse(CamelBaseModel):
    runId: str = Field(..., description="Unique execution run identifier")
    status: Literal["completed", "requires_action", "failed"] = "completed"
    functionCalls: Optional[List[FunctionCall]] = None
    events: List[OrchestratorEvent] = Field(default_factory=list)
    content: List[ContentBlock] = Field(default_factory=list)
    sources: List[SourceReference] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseStreamEvent(CamelBaseModel):
    runId: str
    sequence: int = Field(..., ge=1)


class EventStreamEvent(BaseStreamEvent):
    type: Literal["event"] = "event"
    data: OrchestratorEvent


class TextChunkData(CamelBaseModel):
    content: str


class TextChunkStreamEvent(BaseStreamEvent):
    type: Literal["textChunk"] = "textChunk"
    data: TextChunkData


class FunctionCallStreamEvent(BaseStreamEvent):
    type: Literal["function_call"] = "function_call"
    data: FunctionCall


class MediaStreamEvent(BaseStreamEvent):
    type: Literal["media"] = "media"
    data: ContentBlock

    @model_validator(mode="after")
    def validate_media_block(self):
        if self.data.type == "text":
            raise ValueError("media stream packets require a non-text content block")
        return self


class CompleteStreamEvent(BaseStreamEvent):
    type: Literal["complete"] = "complete"
    data: UnifiedOrchestratorResponse


StreamEvent = Annotated[
    Union[
        EventStreamEvent,
        TextChunkStreamEvent,
        FunctionCallStreamEvent,
        MediaStreamEvent,
        CompleteStreamEvent,
    ],
    Field(discriminator="type"),
]
