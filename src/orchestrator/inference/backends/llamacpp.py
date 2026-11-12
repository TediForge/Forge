"""Optional llama.cpp backend entry point."""

from orchestrator.inference.backends.base import BackendUnavailableError


def create_backend(*args, **kwargs):
    try:
        import llama_cpp
    except ImportError as exc:
        raise BackendUnavailableError(
            "Backend 'llamacpp' is configured but llama-cpp-python is not installed."
        ) from exc
    raise BackendUnavailableError("The llama.cpp adapter is not yet implemented for this deployment.")
