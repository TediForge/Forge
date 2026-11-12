"""Optional SGLang backend entry point."""

from orchestrator.inference.backends.base import BackendUnavailableError


def create_backend(*args, **kwargs):
    try:
        import sglang
    except ImportError as exc:
        raise BackendUnavailableError(
            "Backend 'sglang' is configured but SGLang is not installed."
        ) from exc
    raise BackendUnavailableError("The SGLang adapter is not yet implemented for this deployment.")
