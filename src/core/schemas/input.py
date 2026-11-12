"""
src/schemas/input.py
Defines strict Pydantic input schemas for incoming orchestrator requests,
including base64-encoded file attachments, execution modes, and camelCase aliases.
"""
import base64
import binascii
import hashlib
import os
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from enum import Enum
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class CamelBaseModel(BaseModel):
    """
    Base model configured to automatically support camelCase aliases 
    and population by name.
    """
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore"
    )


class ExecutionMode(str, Enum):
    AUTO = "auto"
    FAST = "fast"
    EXPERT = "expert"


class ExecutionTopology(str, Enum):
    AUTONOMOUS = "autonomous"
    INTERACTIVE = "interactive"


class ExternalToolDefinition(CamelBaseModel):
    type: Literal["function"] = "function"
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9]*$")
    description: str = Field(..., max_length=4000)
    parameters: Dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    strict: bool = True


class FunctionCallOutput(CamelBaseModel):
    type: Literal["function_call_output"] = "function_call_output"
    call_id: str = Field(
        ...,
        min_length=6,
        max_length=80,
        validation_alias=AliasChoices("call_id", "callId"),
        serialization_alias="call_id",
    )
    output: Any


class ReasoningConfig(CamelBaseModel):
    effort: Literal["low", "medium", "high", "xhigh"] = "medium"


class AttachmentType(str, Enum):
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    CODE = "code"
    UNKNOWN = "unknown"


class AttachmentPayload(CamelBaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    fileId: str = Field(..., min_length=1, max_length=200, description="Stable file identifier")
    fileName: str = Field(..., min_length=1, max_length=255, description="Original file name")
    mimeType: str = Field(..., min_length=1, max_length=255, description="Declared media type verified before use")
    fileData: str = Field(..., min_length=1, description="Base64-encoded file bytes")
    attachmentType: AttachmentType = Field(default=AttachmentType.UNKNOWN)
    fileSizeBytes: Optional[int] = Field(default=None, ge=0)
    checksumSha256: Optional[str] = Field(default=None, pattern="^[a-fA-F0-9]{64}$")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Non-secret file metadata")

    @model_validator(mode="after")
    def validate_encoded_file(self):
        maxBytes = int(os.getenv("FORGE_ATTACHMENT_MAX_BYTES", 10 * 1024 * 1024))
        if maxBytes < 1:
            raise ValueError("FORGE_ATTACHMENT_MAX_BYTES must be positive")
        try:
            raw = base64.b64decode(self.fileData, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("fileData must be valid base64") from exc
        if len(raw) > maxBytes:
            raise ValueError(f"decoded fileData exceeds {maxBytes} bytes")
        if self.fileSizeBytes is not None and self.fileSizeBytes != len(raw):
            raise ValueError("fileSizeBytes does not match decoded fileData")
        if self.checksumSha256 and hashlib.sha256(raw).hexdigest().casefold() != self.checksumSha256.casefold():
            raise ValueError("checksumSha256 does not match decoded fileData")
        mime = self.mimeType.casefold()
        if mime.startswith("image/"):
            self.attachmentType = AttachmentType.IMAGE
        elif mime.startswith("audio/"):
            self.attachmentType = AttachmentType.AUDIO
        elif mime.startswith("video/"):
            self.attachmentType = AttachmentType.VIDEO
        elif mime.startswith("text/") or mime in {
            "application/json", "application/xml", "application/pdf",
        }:
            self.attachmentType = (
                AttachmentType.CODE if "python" in mime or "javascript" in mime
                else AttachmentType.DOCUMENT
            )
        else:
            self.attachmentType = AttachmentType.UNKNOWN
        return self


class Message(CamelBaseModel):
    """A conversation turn; its attachments belong to this message."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(..., max_length=8000)
    attachments: List[AttachmentPayload] = Field(default_factory=list, max_length=20)
    messageId: Optional[str] = None
    createdAt: Optional[datetime] = None

    @model_validator(mode="after")
    def cap_attachment_bytes(self):
        total = sum(
            len(base64.b64decode(attachment.fileData, validate=True))
            for attachment in self.attachments
        )
        if total > 20 * 1024 * 1024:
            raise ValueError("message attachments exceed 20 MB total")
        return self


class HistoryMessage(CamelBaseModel):
    messageId: Optional[str] = Field(default=None, description="Persisted conversation message ID")
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., max_length=8000)
    createdAt: Optional[datetime] = None
    attachments: List[AttachmentPayload] = Field(default_factory=list)

    @model_validator(mode="after")
    def cap_history_attachment_bytes(self):
        total = 0
        for item in self.attachments:
            total += len(base64.b64decode(item.fileData, validate=True))
        if total > 20 * 1024 * 1024:
            raise ValueError("history attachments exceed 20 MB total")
        return self


ChatMessage = HistoryMessage


class OrchestratorRequest(CamelBaseModel):
    """
    The master input payload schema received by the Forge orchestrator.
    """
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    messages: List[Union[Message, FunctionCallOutput]] = Field(default_factory=list)
    stream: bool = False
    reasoning: ReasoningConfig = Field(default_factory=ReasoningConfig)
    tools: List[ExternalToolDefinition] = Field(default_factory=list)
    previousResponseId: Optional[str] = Field(
        default=None,
        validation_alias="previous_response_id",
        serialization_alias="previous_response_id",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_messages_and_resume(self):
        trainingExport = self.metadata.get("trainingExport")
        if trainingExport is not None and not isinstance(trainingExport, bool):
            raise ValueError("metadata.trainingExport must be a boolean")
        outputs = [item for item in self.messages if isinstance(item, FunctionCallOutput)]
        if self.previousResponseId:
            if len(outputs) != 1:
                raise ValueError("previous_response_id requires exactly one function_call_output message")
            if self.tools:
                raise ValueError("tools cannot be changed while resuming a response")
            return self
        if outputs:
            raise ValueError("function_call_output messages require previous_response_id")
        if not self.messages:
            raise ValueError("messages must contain at least one conversation turn")
        if not isinstance(self.messages[-1], Message) or self.messages[-1].role != "user":
            raise ValueError("the final message must be from the user")
        totalAttachmentBytes = sum(
            len(base64.b64decode(attachment.fileData, validate=True))
            for message in self.messages
            if isinstance(message, Message)
            for attachment in message.attachments
        )
        if totalAttachmentBytes > 20 * 1024 * 1024:
            raise ValueError("request attachments exceed 20 MB total")
        return self


class ResponsesInputContent(CamelBaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    type: Literal["input_text", "input_image", "input_file"]
    text: Optional[str] = None
    mediaData: Optional[str] = None
    mimeType: Optional[str] = None
    fileId: Optional[str] = Field(default=None, validation_alias=AliasChoices("fileId", "file_id"))
    fileName: Optional[str] = Field(default=None, validation_alias=AliasChoices("fileName", "file_name"))

    @model_validator(mode="after")
    def validate_input_content(self):
        if self.type == "input_text":
            if not self.text:
                raise ValueError("input_text requires text")
            if self.mediaData is not None or self.mimeType is not None:
                raise ValueError("input_text must not carry media fields")
            return self
        if not self.mediaData or not self.mimeType:
            raise ValueError("media input requires base64 mediaData and mimeType")
        if self.type == "input_image" and not self.mimeType.casefold().startswith("image/"):
            raise ValueError("input_image requires an image MIME type")
        try:
            raw = base64.b64decode(self.mediaData, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("mediaData must be valid base64") from exc
        maxBytes = int(os.getenv("FORGE_MEDIA_MAX_BYTES", 20 * 1024 * 1024))
        if maxBytes < 1 or len(raw) > maxBytes:
            raise ValueError(f"decoded mediaData exceeds the {maxBytes}-byte limit")
        return self


class ResponsesInputMessage(CamelBaseModel):
    role: Literal["system", "developer", "user", "assistant"]
    content: Union[str, List[ResponsesInputContent]]


class ResponsesFunctionCallOutput(CamelBaseModel):
    type: Literal["function_call_output"]
    call_id: str = Field(
        ...,
        alias="call_id",
        serialization_alias="call_id",
        validation_alias=AliasChoices("call_id", "callId"),
    )
    output: Any


ResponsesInputItem = Union[ResponsesInputMessage, ResponsesFunctionCallOutput]


class ResponsesRequest(CamelBaseModel):
    """OpenAI Responses-style request with camelCase public field names."""

    model: str = Field(..., min_length=1)
    input: Union[str, List[ResponsesInputItem]]
    instructions: Optional[str] = None
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    toolChoice: Union[str, Dict[str, Any]] = Field(
        default="auto",
        validation_alias=AliasChoices("toolChoice", "tool_choice"),
    )
    previousResponseId: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("previousResponseId", "previous_response_id"),
    )
    maxOutputTokens: Optional[int] = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("maxOutputTokens", "max_output_tokens"),
    )
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    topP: Optional[float] = Field(default=None, gt=0, le=1, validation_alias=AliasChoices("topP", "top_p"))
    stream: bool = False
    store: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
