import asyncio
import base64
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

from orchestrator.context.state import ExecutionState
from orchestrator.attachments import AttachmentDispatcherRouter
from orchestrator.schemas.v1.responses import AttachmentPayload


PNG_DATA = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jO7sAAAAASUVORK5CYII="


def _attachment(file_data=PNG_DATA, mime_type="image/png", size=None):
    return AttachmentPayload(
        fileId="file-1",
        fileName="pixel.png",
        mimeType=mime_type,
        fileData=file_data,
        fileSizeBytes=size,
    )


def test_image_attachment_extracts_ocr_text(monkeypatch):
    monkeypatch.setitem(sys.modules, "pytesseract", SimpleNamespace(image_to_string=lambda image: "recognized text"))
    result = AttachmentDispatcherRouter.extract_content(_attachment())
    assert result.supported
    assert result.content == "recognized text"


def test_oversized_base64_and_mime_mismatch_are_rejected(monkeypatch):
    oversized = _attachment(file_data=base64.b64encode(b"abc").decode())
    monkeypatch.setattr("orchestrator.attachments.MAX_ATTACHMENT_BYTES", 2)
    result = AttachmentDispatcherRouter.extract_content(oversized)
    assert not result.supported and "limit" in result.reason

    monkeypatch.setattr("orchestrator.attachments.MAX_ATTACHMENT_BYTES", 100)
    mismatch = AttachmentDispatcherRouter.extract_content(_attachment(
        file_data=base64.b64encode(b"\xff\xd8\xffabc").decode(),
    ))
    assert not mismatch.supported and "MIME type" in mismatch.reason


def test_attachment_accepts_only_validated_inline_base64(monkeypatch):
    raw = base64.b64decode(PNG_DATA)
    monkeypatch.setitem(
        sys.modules,
        "pytesseract",
        SimpleNamespace(image_to_string=lambda image: "recognized inline image text"),
    )
    attachment = _attachment(
        size=len(raw),
    ).model_copy(update={"checksumSha256": hashlib.sha256(raw).hexdigest()})
    extracted = AttachmentDispatcherRouter.extract_content(attachment)
    assert extracted.supported
    assert extracted.content == "recognized inline image text"


def test_attachment_rejects_urls_and_invalid_base64():
    with pytest.raises(ValueError, match="fileData"):
        AttachmentPayload(
            fileId="file-1",
            fileName="pixel.png",
            mimeType="image/png",
        )
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        AttachmentPayload.model_validate({
            "fileId": "file-1",
            "fileName": "pixel.png",
            "mimeType": "image/png",
            "fileData": PNG_DATA,
            "fileUrl": "https://assets.example.test/pixel.png",
        })
    with pytest.raises(ValueError, match="valid base64"):
        _attachment(file_data="not-base64!!!")


def test_history_attachments_require_inline_bytes():
    from orchestrator.schemas.v1.responses import HistoryMessage

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        HistoryMessage.model_validate({
            "role": "user",
            "content": "Look at this later",
            "attachments": [{
                "fileId": "file-1",
                "fileName": "pixel.png",
                "mimeType": "image/png",
                "fileUrl": "https://assets.example.test/pixel.png",
            }],
        })


def test_attachment_validation_does_not_run_before_authorization():
    from orchestrator.engine.engine import ForgeEngine
    from orchestrator.security.identity import IdentityContextError

    engine = ForgeEngine()
    with pytest.raises(IdentityContextError):
        asyncio.run(engine.run(
            "Describe this image",
            "session-1",
            attachments=[{"fileUrl": "https://assets.example.test/pixel.png"}],
        ))
    asyncio.run(engine.mediaConverter.close())


def test_classifier_and_refiner_receive_extracted_attachment_content():
    from orchestrator.engine.engine import IntentClassifier, IntentResult, PromptRefiner, RefinedPrompt

    prompts = []

    class Dispatcher:
        def generate_structured(self, *, response_schema, prompt, **kwargs):
            prompts.append(prompt)
            if response_schema is IntentResult:
                return {
                    "reasoning": "image question",
                    "modalities_involved": ["vision"],
                    "primary_capability": "visionInspection",
                    "extracted_prompt": "Describe it",
                }
            return {
                "original_prompt": "Describe it",
                "refined_prompt": "Describe the image",
                "objective": "Describe",
                "modality_profile": "vision",
            }

    dispatcher = Dispatcher()
    context = "## Attachment contents\n### pixel.png (file-1)\nrecognized words"
    intent = IntentClassifier(dispatcher).classify(
        "What is shown?", ["pixel.png"], context=context,
    )
    PromptRefiner(dispatcher).refine(
        "What is shown?",
        intent,
        ["pixel.png"],
        attachmentContents=[{"fileId": "file-1", "fileName": "pixel.png", "content": "recognized words"}],
        historyBlock="## Conversation so far\nuser: earlier question",
    )
    assert "recognized words" in prompts[0]
    assert "recognized words" in prompts[1]
    assert "earlier question" in prompts[1]


def test_attachment_content_is_excluded_from_checkpoint_json():
    state = ExecutionState("run-1", {
        "attachmentContents": [{"fileId": "file-1", "content": "private text"}],
        "inlineAttachments": [{"fileId": "file-1", "mediaData": PNG_DATA}],
        "sessionHistory": [{"content": "private history"}],
        "refinedPrompt": {"refined_prompt": "private extracted text"},
    })
    checkpoint = json.dumps(state.exportState())
    assert "attachmentContents" not in checkpoint
    assert "inlineAttachments" not in checkpoint
    assert "sessionHistory" not in checkpoint
    assert "refinedPrompt" not in checkpoint
    assert "private" not in checkpoint
    assert PNG_DATA not in checkpoint


def test_online_image_reaches_vision_as_base64_without_persisting_media(monkeypatch):
    from orchestrator.engine.engine import (
        ExecutionPlan,
        ExecutionStep,
        ForgeEngine,
        IntentResult,
        RefinedPrompt,
    )
    from orchestrator.security.identity import Principal

    raw = base64.b64decode(PNG_DATA)
    observed = {}
    checkpointSnapshots = []

    class VisionDispatcher:
        def analyze_image(self, *, prompt, system_prompt, images):
            observed["prompt"] = prompt
            observed["images"] = images
            return "A one-pixel image"

    class Checkpoints:
        def save(self, tenant_id, run_id, status, snapshot):
            checkpointSnapshots.append(snapshot)

    class Audit:
        def record(self, *args, **kwargs):
            pass

    monkeypatch.setitem(
        sys.modules,
        "pytesseract",
        SimpleNamespace(image_to_string=lambda image: "recognized text"),
    )
    engine = ForgeEngine(
        text_dispatcher=VisionDispatcher(),
        dispatcher_registry={"vision": VisionDispatcher()},
        audit_log=Audit(),
        checkpoint_store=Checkpoints(),
    )
    async def classify_async(**kwargs):
        return IntentResult(
            reasoning="Image question",
            modalities_involved=["vision"],
            primary_capability="visionInspection",
            extracted_prompt="Describe the image",
        )

    async def refine_async(prompt, intent, attachments, **kwargs):
        return RefinedPrompt(
            original_prompt=prompt,
            refined_prompt="Describe the image",
            objective="Describe the image",
            modality_profile="vision",
        )

    async def create_plan_async(**kwargs):
        return ExecutionPlan(
            reasoning="Inspect the attached image",
            steps=[ExecutionStep(
                step_id=1,
                modality="vision",
                capability="visionInspection",
                task_instruction="Describe the image",
            )],
        )

    engine.intentClassifier = SimpleNamespace(classify_async=classify_async)
    engine.promptRefiner = SimpleNamespace(refine_async=refine_async)
    engine.executionPlanner = SimpleNamespace(create_plan_async=create_plan_async)
    attachment = AttachmentPayload(
        fileId="file-1",
        fileName="pixel.png",
        mimeType="image/png",
        fileData=PNG_DATA,
        fileSizeBytes=len(raw),
    )

    response = asyncio.run(engine.run(
        "Describe this image",
        "session-vision",
        principal=Principal("user-1", "tenant-a", roles=("operator",)),
        attachments=[attachment],
    ))

    assert response.status == "completed"
    assert observed["images"] == [{
        "fileId": "file-1",
        "fileName": "pixel.png",
        "mimeType": "image/png",
        "mediaData": PNG_DATA,
    }]
    serializedSnapshots = json.dumps(checkpointSnapshots)
    assert PNG_DATA not in serializedSnapshots


def test_vision_image_requires_multimodal_dispatcher():
    from orchestrator.agents.base import AgentExecutionError
    from orchestrator.agents.vision.agent import VisionAgent

    state = ExecutionState("run-vision", {
        "inlineAttachments": [{
            "fileId": "file-1",
            "fileName": "pixel.png",
            "mimeType": "image/png",
            "mediaData": PNG_DATA,
        }],
    })
    with pytest.raises(AgentExecutionError, match="analyze_image support"):
        asyncio.run(VisionAgent().execute("Describe the image", state))
