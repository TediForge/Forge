"""Optional OpenAI-compatible remote backend entry point."""

from orchestrator.inference.backends.base import BackendUnavailableError


def create_backend(*args, **kwargs):
    raise BackendUnavailableError(
        "Backend 'remote' requires an explicit OpenAI-compatible adapter and base URL; none is configured."
    )
