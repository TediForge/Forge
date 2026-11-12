"""Health and readiness endpoints for the orchestrator service."""

import tempfile

from fastapi import APIRouter, HTTPException, Request

from orchestrator.settings import get_settings


router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness(request: Request) -> dict[str, object]:
    settings = get_settings()
    gateway = getattr(request.app.state, "modelGateway", None)
    if gateway is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "model_gateway_unavailable", "message": "Model gateway is unavailable."},
        )
    checkpoint_root = settings.resolved_checkpoint_root
    try:
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=checkpoint_root):
            pass
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "checkpoint_storage_unavailable", "message": "Checkpoint storage is not writable."},
        ) from exc
    models = gateway.readiness()
    if models["status"] != "ready":
        raise HTTPException(
            status_code=503,
            detail={
                "code": "models_not_ready",
                "message": "Required local model weights are not available.",
                "models": models["missingModels"],
            },
        )
    return {
        "status": "ready",
        "checkpointStorage": "writable",
        "models": models,
    }
