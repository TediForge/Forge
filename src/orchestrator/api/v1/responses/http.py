"""HTTP surface for the orchestrator-owned Responses API."""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from orchestrator.engine.engine import ForgeEngine, RequestContractError
from orchestrator.agents.base import AgentExecutionError
from orchestrator.context.limits import ExecutionLimitError
from orchestrator.inference.modalities import DispatcherError
from orchestrator.media import MediaConversionError
from orchestrator.schemas.v1.responses import (
    CompleteStreamEvent,
    EventStreamEvent,
    FunctionCallStreamEvent,
    MediaStreamEvent,
    TextChunkData,
    TextChunkStreamEvent,
    FunctionCallOutput,
    Message,
    OrchestratorRequest,
    UnifiedOrchestratorResponse,
)
from orchestrator.security.identity import IdentityContextError, Principal
from orchestrator.security.rbac import AuthorizationError


router = APIRouter()
logger = logging.getLogger(__name__)


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(status_code=401, detail="Authenticated principal is required.")
    return principal


def _engine(request: Request) -> ForgeEngine:
    engine = getattr(request.app.state, "engine", None)
    if not isinstance(engine, ForgeEngine):
        raise HTTPException(status_code=503, detail="Responses engine is unavailable.")
    return engine


async def _response_stream(response: UnifiedOrchestratorResponse):
    sequence = 0
    for event in response.events:
        sequence += 1
        packet = EventStreamEvent(runId=response.runId, sequence=sequence, data=event)
        yield f"event: event\nid: {response.runId}:{sequence}\ndata: {packet.model_dump_json(by_alias=True, exclude_none=True)}\n\n"
    for call in response.functionCalls or []:
        sequence += 1
        packet = FunctionCallStreamEvent(runId=response.runId, sequence=sequence, data=call)
        yield f"event: function_call\nid: {response.runId}:{sequence}\ndata: {packet.model_dump_json(by_alias=True)}\n\n"
    if response.status != "requires_action":
        for block in response.content:
            sequence += 1
            if block.type == "text":
                packet = TextChunkStreamEvent(
                    runId=response.runId,
                    sequence=sequence,
                    data=TextChunkData(content=block.text or ""),
                )
                eventType = "textChunk"
            else:
                packet = MediaStreamEvent(runId=response.runId, sequence=sequence, data=block)
                eventType = "media"
            yield f"event: {eventType}\nid: {response.runId}:{sequence}\ndata: {packet.model_dump_json(by_alias=True, exclude_none=True)}\n\n"
    sequence += 1
    complete = CompleteStreamEvent(
        runId=response.runId,
        sequence=sequence,
        data=response.model_dump(by_alias=True, exclude_none=True),
    )
    yield f"event: complete\nid: {response.runId}:{sequence}\ndata: {complete.model_dump_json(by_alias=True, exclude_none=True)}\n\n"


@router.post("/v1/responses", response_model=UnifiedOrchestratorResponse)
async def create_response(payload: OrchestratorRequest, request: Request):
    principal = _principal(request)
    engine = _engine(request)
    try:
        if payload.previousResponseId:
            outputs = [item for item in payload.messages if isinstance(item, FunctionCallOutput)]
            response = await engine.resume(
                payload.previousResponseId,
                outputs,
                principal=principal,
                include_suggestions=payload.includeSuggestions,
            )
            if payload.stream:
                return StreamingResponse(_response_stream(response), media_type="text/event-stream")
            return JSONResponse(response.model_dump(by_alias=True, exclude_none=True))
        messages = [item for item in payload.messages if isinstance(item, Message)]
        if not messages:
            raise RequestContractError("A new response requires at least one conversation message.")
        result = await engine.run(
            prompt=messages[-1].content,
            stream=payload.stream,
            attachments=messages[-1].attachments,
            history=messages[:-1],
            principal=principal,
            external_tools=payload.tools,
            reasoning_effort=payload.reasoning.effort,
            trajectory_export=payload.trajectoryExport,
            include_suggestions=payload.includeSuggestions,
        )
        if payload.stream:
            return StreamingResponse(result, media_type="text/event-stream")
        return JSONResponse(result.model_dump(by_alias=True, exclude_none=True))
    except RequestContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IdentityContextError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ExecutionLimitError as exc:
        return _error_response(422, "execution_limit", str(exc))
    except MediaConversionError as exc:
        return _error_response(422, exc.code, str(exc))
    except AgentExecutionError:
        logger.warning("Agent execution failed", extra={"request_id": getattr(request.state, "request_id", None)})
        return _error_response(503, "agent_unavailable", "The requested agent could not complete the run.")
    except DispatcherError:
        logger.warning("Model dispatcher failed", extra={"request_id": getattr(request.state, "request_id", None)})
        return _error_response(503, "model_unavailable", "The configured model could not complete the run.")
    except RuntimeError:
        logger.warning("Orchestration runtime unavailable", extra={"request_id": getattr(request.state, "request_id", None)})
        return _error_response(503, "runtime_unavailable", "The orchestration runtime is unavailable.")
    except Exception:
        logger.exception("Responses request failed", extra={"request_id": getattr(request.state, "request_id", None)})
        return _error_response(500, "internal_error", "The request could not be completed.")
