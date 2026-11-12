"""HTTP surface for the orchestrator-owned Responses API."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.api.v1.responses.routes import ForgeEngine, RequestContractError
from src.core.schemas.input import (
    ExecutionMode,
    FunctionCallOutput,
    Message,
    OrchestratorRequest,
)
from src.core.schemas.output import (
    CompleteStreamEvent,
    EventStreamEvent,
    FunctionCallStreamEvent,
    MediaStreamEvent,
    TextChunkData,
    TextChunkStreamEvent,
    UnifiedOrchestratorResponse,
)
from src.core.security.identity import IdentityContextError, Principal
from src.core.security.rbac import AuthorizationError


router = APIRouter()


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
            )
            if payload.stream:
                return StreamingResponse(_response_stream(response), media_type="text/event-stream")
            return JSONResponse(response.model_dump(by_alias=True, exclude_none=True))
        messages = [item for item in payload.messages if isinstance(item, Message)]
        if not messages:
            raise RequestContractError("A new response requires at least one conversation message.")
        trainingExport = payload.metadata.get("trainingExport", False)
        effortMode = {
            "low": ExecutionMode.FAST,
            "medium": ExecutionMode.AUTO,
            "high": ExecutionMode.EXPERT,
            "xhigh": ExecutionMode.EXPERT,
        }[payload.reasoning.effort]
        result = await engine.run(
            prompt=messages[-1].content,
            stream=payload.stream,
            attachments=messages[-1].attachments,
            history=messages[:-1],
            principal=principal,
            external_tools=payload.tools,
            mode=effortMode,
            training_export=trainingExport,
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
