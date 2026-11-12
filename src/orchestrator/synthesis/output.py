"""Build ordered, redacted public response and stream contracts."""

import json
from collections.abc import AsyncGenerator
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from opentelemetry import trace

from orchestrator.schemas.v1.responses import (
    ActionRecord,
    CompleteStreamEvent,
    ContentBlock,
    EventStreamEvent,
    FunctionCall,
    FunctionCallStreamEvent,
    OrchestratorEvent,
    RunStatus,
    SourceReference,
    StreamEvent,
    TextChunkData,
    TextChunkStreamEvent,
    MediaStreamEvent,
    TerminalStatus,
    Thought,
    UnifiedOrchestratorResponse,
)
from orchestrator.security.audit import redact
from orchestrator.synthesis.aggregator import aggregate_output_items
from orchestrator.synthesis.errors import apply_failure_policy
from orchestrator.synthesis.formatter import to_chat_completion, to_responses
from orchestrator.synthesis.normalizer import normalize_media_assets, normalize_sources


tracer = trace.get_tracer("orchestrator.synthesis")


class OutputSynthesizer:
    @staticmethod
    def normalizeStatus(status: Optional[str] = None) -> str:
        normalized = str(status or TerminalStatus.COMPLETED.value).lower()
        if normalized == "success":
            return TerminalStatus.COMPLETED.value
        valid = {item.value for item in TerminalStatus}
        return normalized if normalized in valid else TerminalStatus.FAILED.value

    @staticmethod
    def _contentBlocks(content: Any, mediaAssets: list[dict[str, Any]]) -> list[ContentBlock]:
        blocks: list[ContentBlock] = []
        if isinstance(content, str) and content.strip():
            blocks.append(ContentBlock(type="text", text=content.strip()))
        elif isinstance(content, list):
            blocks.extend(
                item if isinstance(item, ContentBlock) else ContentBlock.model_validate(item)
                for item in content
            )
        for item in mediaAssets:
            media_type = str(item.get("mediaType", item.get("type", "file"))).casefold()
            blocks.append(ContentBlock.model_validate({
                "type": media_type,
                "assetId": item.get("assetId"),
                "mediaData": item.get("mediaData"),
                "mimeType": item.get("mimeType"),
                "fileName": item.get("fileName"),
                "fileSizeBytes": item.get("fileSizeBytes"),
                "altText": item.get("altText"),
                "metadata": redact(item.get("metadata") or {}),
            }))
        return blocks

    @staticmethod
    def _orderedEvents(
        events: list[dict[str, Any]] | None,
        reasoningLogs: list[dict[str, Any]] | None,
        actions: list[dict[str, Any]] | None,
        responseStatus: str | None,
        status: str,
        terminationReason: str | None,
        metrics: dict[str, Any],
    ) -> list[OrchestratorEvent]:
        raw_events: list[Any] = list(events or [])
        if events is None:
            raw_events.extend(reasoningLogs or [])
            raw_events.extend(actions or [])
        result: list[OrchestratorEvent] = []
        for raw in raw_events:
            if not isinstance(raw, dict):
                continue
            kind = raw.get("type")
            data = raw
            if not any(key in raw for key in ("id", "actionId", "status")):
                data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
            try:
                if kind == "thought" or "id" in data and "message" in data:
                    result.append(OutputSynthesizer._publicThought(data))
                elif kind == "action" or "actionId" in data:
                    result.append(ActionRecord.model_validate(data).model_copy(update={
                        "metadata": redact(data.get("metadata", {})),
                        "error": redact(data.get("error")) if data.get("error") else None,
                    }))
                elif kind == "status" or "terminationReason" in data:
                    result.append(RunStatus.model_validate(data))
            except ValidationError:
                continue
        final_status = responseStatus if responseStatus in {"requires_action", "failed"} else status
        if final_status in {"requires_action", "failed"} and not (
            result and isinstance(result[-1], RunStatus) and result[-1].status == final_status
        ):
            result.append(RunStatus(
                status=final_status,
                terminationReason=terminationReason,
                stepCount=metrics.get("stepsExecuted"),
                toolCallCount=metrics.get("toolCalls"),
            ))
        return result

    @staticmethod
    def synthesizeStatic(
        runId: str,
        content: Any,
        reasoningLogs: Optional[List[Dict[str, Any]]] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        sources: Optional[List[SourceReference | Dict[str, Any]]] = None,
        mediaAssets: Optional[List[dict[str, Any]]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        terminationReason: Optional[str] = None,
        outputItems: Optional[List[Dict[str, Any]]] = None,
        failures: Optional[List[Any]] = None,
        allowPartial: bool = True,
        responseStatus: Optional[str] = None,
        functionCalls: Optional[List[FunctionCall]] = None,
        events: Optional[List[dict[str, Any]]] = None,
    ) -> UnifiedOrchestratorResponse:
        aggregate = aggregate_output_items(outputItems)
        if not content:
            content = aggregate.content
        normalized_sources = normalize_sources([sources or [], aggregate.sources])
        normalized_media = normalize_media_assets([mediaAssets or [], aggregate.media_assets])
        publicMetadata = dict(metrics or {})
        normalized_status = (
            TerminalStatus.COMPLETED.value
            if responseStatus == "requires_action"
            else OutputSynthesizer.normalizeStatus(status or publicMetadata.get("status"))
        )
        text_content = content if isinstance(content, str) else "".join(
            block.text or "" for block in content if isinstance(block, ContentBlock) and block.type == "text"
        )
        text_content, normalized_status, failure_metadata = apply_failure_policy(
            text_content, normalized_status, failures or aggregate.failures, allowPartial,
        )
        publicMetadata.update(failure_metadata)
        publicMetadata["status"] = normalized_status
        if terminationReason:
            publicMetadata["terminationReason"] = terminationReason
        if not isinstance(content, list):
            content_blocks = OutputSynthesizer._contentBlocks(text_content, normalized_media)
        else:
            content_blocks = OutputSynthesizer._contentBlocks(content, normalized_media)
        return UnifiedOrchestratorResponse(
            runId=runId,
            events=OutputSynthesizer._orderedEvents(
                events, reasoningLogs, actions, responseStatus, normalized_status, terminationReason, publicMetadata,
            ),
            content=content_blocks,
            sources=normalized_sources,
            metadata=redact(publicMetadata),
            status=responseStatus or ("failed" if normalized_status == "failed" else "completed"),
            functionCalls=functionCalls,
        )

    @staticmethod
    def toResponses(response: UnifiedOrchestratorResponse, outputItems=None, model: str = "forge", createdAt: int | None = None) -> Dict[str, Any]:
        aggregate = aggregate_output_items(outputItems)
        text = "".join(block.text or "" for block in response.content if block.type == "text")
        normalized = response.model_copy(update={
            "sources": normalize_sources([response.sources, aggregate.sources]),
            "content": OutputSynthesizer._contentBlocks(response.content, aggregate.media_assets),
        })
        if text != "".join(block.text or "" for block in normalized.content if block.type == "text"):
            normalized.content.insert(0, ContentBlock(type="text", text=text))
        return to_responses(normalized, aggregate.output_items, model, createdAt)

    @staticmethod
    def toChatCompletion(response: UnifiedOrchestratorResponse, model: str = "forge", created: int | None = None, toolCalls=None) -> Dict[str, Any]:
        return to_chat_completion(response, model, created, toolCalls)

    @staticmethod
    def _publicThought(item: Dict[str, Any]) -> Thought:
        message = str(item.get("message") or "Progress update").strip().rstrip(".!?") or "Progress update"
        thought_status = item.get("status", "completed")
        if thought_status not in {"started", "processing", "completed"}:
            thought_status = "completed"
        return Thought(
            id=str(item.get("id") or "T9N3Q7"),
            message=message,
            status=thought_status,
            data=redact(item.get("data") if isinstance(item.get("data"), dict) else {}),
        )

    @staticmethod
    async def synthesizeStream(
        runId: str,
        executionGenerator: AsyncGenerator[Dict[str, Any], None],
        content: str = "",
        sources: Optional[List[Dict[str, Any]]] = None,
        mediaAssets: Optional[List[Dict[str, Any]]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        terminationReason: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        with tracer.start_as_current_span("orchestrator.synthesize_stream"):
            synthesized = OutputSynthesizer._synthesizeStream(
                runId,
                executionGenerator,
                content,
                sources,
                mediaAssets,
                metrics,
                status,
                terminationReason,
            )
            try:
                async for frame in synthesized:
                    yield frame
            finally:
                await synthesized.aclose()
                await executionGenerator.aclose()

    @staticmethod
    async def _synthesizeStream(
        runId: str,
        executionGenerator: AsyncGenerator[Dict[str, Any], None],
        content: str = "",
        sources: Optional[List[Dict[str, Any]]] = None,
        mediaAssets: Optional[List[Dict[str, Any]]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        terminationReason: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        allowedEvents = {"thought", "action", "status", "textChunk", "function_call", "media"}
        sequence = 0
        assembled_text = content
        events: list[OrchestratorEvent] = []
        function_calls: list[FunctionCall] = []
        content_blocks: list[ContentBlock] = []
        if content.strip():
            content_blocks.append(ContentBlock(type="text", text=content.strip()))
        collected_sources = list(sources or [])
        collected_media = list(mediaAssets or [])
        final_status = status
        final_metrics = dict(metrics or {})
        async for stepOutput in executionGenerator:
            eventType = stepOutput.get("type", "status")
            data = redact(stepOutput.get("data", {}))
            if eventType == "source":
                collected_sources.append(data)
                continue
            if eventType == "mediaAsset":
                collected_media.append(data)
                continue
            if eventType == "toolCall" or eventType not in allowedEvents:
                continue
            if eventType == "textChunk":
                text = str(data.get("content", data.get("textChunk", data.get("chunk", ""))))
                assembled_text += text
                chunkData = TextChunkData(content=text)
                packet = TextChunkStreamEvent(
                    runId=runId, sequence=sequence + 1, data=chunkData,
                )
                if text:
                    content_blocks.append(ContentBlock(type="text", text=text))
            elif eventType == "thought":
                thought = OutputSynthesizer._publicThought(data)
                events.append(thought)
                packet = EventStreamEvent(runId=runId, sequence=sequence + 1, data=thought)
            elif eventType == "action":
                action = ActionRecord.model_validate(data).model_copy(update={
                    "metadata": redact(data.get("metadata", {})),
                    "error": redact(data.get("error")) if data.get("error") else None,
                })
                events.append(action)
                packet = EventStreamEvent(runId=runId, sequence=sequence + 1, data=action)
            elif eventType == "status":
                status_record = RunStatus.model_validate(data)
                events.append(status_record)
                packet = EventStreamEvent(runId=runId, sequence=sequence + 1, data=status_record)
                if status_record.status in {"failed", "requires_action"}:
                    final_status = status_record.status
                if status_record.terminationReason:
                    terminationReason = status_record.terminationReason
            elif eventType == "media":
                block = ContentBlock.model_validate(data)
                packet = MediaStreamEvent(runId=runId, sequence=sequence + 1, data=block)
                content_blocks.append(block)
            elif eventType == "function_call":
                function_call = FunctionCall.model_validate(data)
                function_calls.append(function_call)
                packet = FunctionCallStreamEvent(
                    runId=runId, sequence=sequence + 1, data=function_call,
                )
            sequence += 1
            packetType = "event" if eventType in {"thought", "action", "status"} else eventType
            yield f"event: {packetType}\nid: {runId}:{sequence}\ndata: {packet.model_dump_json(by_alias=True, exclude_none=True)}\n\n"
        response = UnifiedOrchestratorResponse(
            runId=runId,
            status=final_status if final_status in {"failed", "requires_action"} else "completed",
            events=events,
            content=content_blocks,
            sources=normalize_sources(collected_sources),
            metadata=redact(final_metrics | {"status": final_status or "completed"}),
            functionCalls=function_calls or None,
        )
        sequence += 1
        completePacket = CompleteStreamEvent(
            runId=runId,
            sequence=sequence,
            data=response.model_dump(by_alias=True, exclude_none=True),
        )
        yield f"event: complete\nid: {runId}:{sequence}\ndata: {completePacket.model_dump_json(by_alias=True, exclude_none=True)}\n\n"
