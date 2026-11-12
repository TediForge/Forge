"""Optional TensorRT-LLM backend entry point."""

from orchestrator.inference.backends.base import BackendUnavailableError


def create_backend(*args, **kwargs):
    try:
        import tensorrt_llm
    except ImportError as exc:
        raise BackendUnavailableError(
            "Backend 'tensorrt' is configured but TensorRT-LLM is not installed."
        ) from exc
    raise BackendUnavailableError("The TensorRT-LLM adapter is not yet implemented for this deployment.")
