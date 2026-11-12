"""FastAPI application assembled from versioned API routers."""

from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.api.v1.chat.completions.routes import router as chat_completions_router
from src.api.v1.embeddings.routes import router as embeddings_router
from src.api.v1.audio.speech.routes import router as speech_router
from src.api.v1.audio.sts.routes import router as sts_router
from src.api.v1.audio.transcriptions.routes import router as transcriptions_router
from src.api.v1.models.routes import router as models_router
from src.api.v1.responses.http import router as responses_router
from src.api.v1.responses.routes import ForgeEngine


@asynccontextmanager
async def lifespan(application: FastAPI):
    engine = ForgeEngine()
    application.state.engine = engine
    application.state.localModelProviders = {}
    try:
        yield
    finally:
        for provider in application.state.localModelProviders.values():
            await provider.close()
        await engine.dispatcherRegistry["audio"].close()
        await engine.dispatcherRegistry["stt"].close()
        await engine.trainingExporter.shutdown()
        await engine.mediaConverter.close()


app = FastAPI(title="Forge Orchestrator", version="1.0.0", lifespan=lifespan)
app.include_router(responses_router)
app.include_router(chat_completions_router)
app.include_router(models_router)
app.include_router(embeddings_router)
app.include_router(transcriptions_router)
app.include_router(speech_router)
app.include_router(sts_router)