"""Typed errors for computer runtime failures."""


class ComputerError(RuntimeError):
    """Base error for computer execution and lifecycle failures."""


class ComputerUnavailableError(ComputerError):
    """The host or guest runtime is unavailable or not configured."""


class ComputerPolicyError(ComputerError):
    """A computer operation violates the runtime policy."""
