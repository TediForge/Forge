"""FastAPI application assembled from versioned API routers."""

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response

from orchestrator.api.v1.health import router as health_router
from orchestrator.api.v1.chat.completions.routes import router as chat_completions_router
from orchestrator.api.v1.embeddings.routes import router as embeddings_router
from orchestrator.api.v1.audio.speech.routes import router as speech_router
from orchestrator.api.v1.audio.sts.routes import router as sts_router
from orchestrator.api.v1.audio.transcriptions.routes import router as transcriptions_router
from orchestrator.api.v1.models.routes import router as models_router
from orchestrator.api.v1.responses.http import router as responses_router
from orchestrator.engine.engine import ForgeEngine
from orchestrator.context.metrics import RuntimeMetrics
from orchestrator.context.tracing import configure_tracing
from orchestrator.inference.modalities import CanvasDispatcher, SttDispatcher, TextDispatcher, VoiceDispatcher
from orchestrator.inference.gateway import InferenceGateway
from orchestrator.settings import get_settings


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    if settings.environment == "production" and settings.checkpoint_root is None:
        raise RuntimeError("FORGE_CHECKPOINT_ROOT must be set in production")
    application.state.tracerProvider = configure_tracing(settings.otlp_endpoint)
    gateway = InferenceGateway()
    metrics = RuntimeMetrics()
    dispatchers = {
        "text": TextDispatcher(gateway.get("text")),
        "image": CanvasDispatcher(gateway.get("image")),
        "audio": VoiceDispatcher(gateway.get("audio")),
        "stt": SttDispatcher(gateway.get("transcription")),
    }
    engine = ForgeEngine(
        text_dispatcher=dispatchers["text"],
        dispatcher_registry=dispatchers,
        metrics=metrics,
        inference_gateway=gateway,
    )
    application.state.engine = engine
    application.state.modelGateway = gateway
    application.state.inferenceGateway = gateway
    application.state.metrics = metrics
    try:
        yield
    finally:
        results = await asyncio.gather(engine.close(), gateway.close(), return_exceptions=True)
        errors = [result for result in results if isinstance(result, BaseException)]
        if errors:
            raise ExceptionGroup("Application resources failed to close", errors)


app = FastAPI(title="Forge Orchestrator", version="1.0.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(responses_router)
app.include_router(chat_completions_router)
app.include_router(models_router)
app.include_router(embeddings_router)
app.include_router(transcriptions_router)
app.include_router(speech_router)
app.include_router(sts_router)


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint(request: Request) -> Response:
    metrics = getattr(request.app.state, "metrics", None)
    if metrics is None:
        raise HTTPException(status_code=503, detail="Metrics are unavailable.")
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")


@app.middleware("http")
async def request_observability(request, call_next):
    supplied_id = request.headers.get("x-request-id", "")
    request_id = supplied_id if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied_id) else None
    request_id = request_id or f"req_{time.time_ns():x}"
    request.state.request_id = request_id
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        logger.info(
            "http.request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )