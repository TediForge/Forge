"""Classify and extract bounded text from base64 input attachments."""

import base64
import binascii
import io
import logging
from dataclasses import dataclass
from typing import Dict, Any

from PIL import Image

from orchestrator.schemas.v1.responses import AttachmentPayload, AttachmentType
from orchestrator.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AttachmentContent:
    content: str
    supported: bool = True
    reason: str | None = None


class AttachmentDispatcherRouter:
    """
    Analyzes attachments and assigns the appropriate processing tool 
    based on file type and modality requirements.
    """

    SUPPORTED_MIME_MAP = {
        # Images -> Vision / OCR
        "image/png": {"type": AttachmentType.IMAGE, "capability": "visionInspection", "dispatcher": "vision"},
        "image/jpeg": {"type": AttachmentType.IMAGE, "capability": "visionInspection", "dispatcher": "vision"},
        "image/webp": {"type": AttachmentType.IMAGE, "capability": "visionInspection", "dispatcher": "vision"},
        
        # Documents -> OCR / Text Extraction / Parsing
        "application/pdf": {"type": AttachmentType.DOCUMENT, "capability": "documentParsing", "dispatcher": "visionText"},
        "text/plain": {"type": AttachmentType.DOCUMENT, "capability": "textExtraction", "dispatcher": "text"},
        "application/json": {"type": AttachmentType.DOCUMENT, "capability": "codeAnalysis", "dispatcher": "text"},
        
        # Audio -> Speech Transcription
        "audio/mpeg": {"type": AttachmentType.AUDIO, "capability": "speechToText", "dispatcher": "audio"},
        "audio/wav": {"type": AttachmentType.AUDIO, "capability": "speechToText", "dispatcher": "audio"},
        "audio/ogg": {"type": AttachmentType.AUDIO, "capability": "speechToText", "dispatcher": "audio"},
        
        # Code Files -> Code Interpreter / Analysis
        "text/x-python": {"type": AttachmentType.CODE, "capability": "codeExecution", "dispatcher": "codeInterpreter"},
        "application/javascript": {"type": AttachmentType.CODE, "capability": "codeAnalysis", "dispatcher": "text"}
    }

    @classmethod
    def extract_content(cls, attachment: AttachmentPayload) -> AttachmentContent:
        if attachment.fileData is None:
            return AttachmentContent("", False, "Attachment must be converted to base64 before extraction")
        maxBytes = get_settings().attachment_max_bytes
        try:
            raw = base64.b64decode(attachment.fileData, validate=True)
        except (binascii.Error, ValueError) as exc:
            return AttachmentContent("", False, "Attachment data is not valid base64")
        if len(raw) > maxBytes or (attachment.fileSizeBytes is not None and attachment.fileSizeBytes > maxBytes):
            return AttachmentContent("", False, f"Attachment exceeds the {maxBytes}-byte limit")
        if attachment.fileSizeBytes is not None and attachment.fileSizeBytes != len(raw):
            return AttachmentContent("", False, "Attachment size does not match fileSizeBytes")

        mime = attachment.mimeType.casefold()
        signatures = {
            "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
            "image/webp": len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP",
            "application/pdf": raw.startswith(b"%PDF-"),
            "audio/wav": raw.startswith(b"RIFF") and raw[8:12] == b"WAVE",
            "audio/ogg": raw.startswith(b"OggS"),
            "audio/mpeg": raw.startswith(b"ID3") or raw[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"},
        }
        if mime in signatures and not signatures[mime]:
            return AttachmentContent("", False, f"File bytes do not match MIME type {attachment.mimeType}")

        if mime.startswith("image/"):
            if mime not in {"image/png", "image/jpeg", "image/webp"}:
                return AttachmentContent("", False, f"Unsupported image MIME type: {attachment.mimeType}")
            try:
                import pytesseract

                with Image.open(io.BytesIO(raw)) as image:
                    return AttachmentContent(pytesseract.image_to_string(image).strip())
            except ImportError:
                return AttachmentContent("", False, "Image OCR dependencies are unavailable")
            except Exception as exc:
                logger.warning("Attachment OCR failed for %s: %s", attachment.fileId, type(exc).__name__)
                return AttachmentContent("", False, "Image text extraction failed")

        if mime == "application/pdf":
            return AttachmentContent("", False, "PDF text extraction is not configured")
        if mime.startswith("text/") or mime in {"application/json", "application/xml"} or attachment.attachmentType == AttachmentType.CODE:
            try:
                return AttachmentContent(raw.decode("utf-8").strip())
            except UnicodeDecodeError:
                return AttachmentContent("", False, "Text attachment is not valid UTF-8")
        if mime.startswith("audio/") or attachment.attachmentType == AttachmentType.AUDIO:
            return AttachmentContent(f"[audio: {attachment.mimeType}, {len(raw)} bytes]")
        if mime.startswith("video/") or attachment.attachmentType == AttachmentType.VIDEO:
            return AttachmentContent(f"[video: {attachment.mimeType}, {len(raw)} bytes]")
        return AttachmentContent("", False, f"Unsupported MIME type: {attachment.mimeType}")

    @classmethod
    def resolveToolForAttachment(cls, attachment: AttachmentPayload) -> Dict[str, Any]:
        """
        Examines file MIME type and routes to the correct processing tool route.
        """
        config = cls.SUPPORTED_MIME_MAP.get(attachment.mimeType)

        if not config:
            # Fallback for unrecognized formats
            return {
                "attachmentType": AttachmentType.UNKNOWN,
                "targetCapability": "genericFileHandling",
                "targetDispatcher": "text",
                "supported": False,
                "routingNote": f"Unsupported MIME type: {attachment.mimeType}"
            }

        # Update the attachment payload's categorized type
        attachment.attachmentType = config["type"]

        return {
            "attachmentType": config["type"],
            "targetCapability": config["capability"],
            "targetDispatcher": config["dispatcher"],
            "supported": True,
            "routingNote": f"Routed {attachment.fileName} to {config['dispatcher']} dispatcher via {config['capability']}."
        }