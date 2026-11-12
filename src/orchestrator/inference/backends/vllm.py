"""Optional vLLM backend; installation is required only when configured."""

from orchestrator.inference.backends.base import BackendUnavailableError


def create_backend(*args, **kwargs):
    try:
        import vllm
    except ImportError as exc:
        raise BackendUnavailableError(
            "Backend 'vllm' is configured but vLLM is not installed; install the optional vLLM extra."
        ) from exc
    raise BackendUnavailableError("The vLLM adapter is not yet implemented for this deployment.")
