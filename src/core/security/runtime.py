"""Production identity mode controls."""

import os

from src.core.security.identity import IdentityContextError, Principal


class ProductionIdentityResolver:
    def __init__(self, allow_anonymous: bool | None = None) -> None:
        if allow_anonymous is None:
            allow_anonymous = os.getenv("FORGE_ALLOW_ANONYMOUS", "false").lower() == "true"
        self.allow_anonymous = allow_anonymous

    def resolve(self, user_id: str | None, tenant_id: str | None, roles: list[str] | None = None) -> Principal | None:
        if user_id and tenant_id:
            return Principal(user_id=user_id, tenant_id=tenant_id, roles=tuple(roles or ["operator"]))
        if self.allow_anonymous:
            return None
        raise IdentityContextError("Authenticated user and tenant claims are required")
