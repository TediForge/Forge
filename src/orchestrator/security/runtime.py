"""Production identity mode controls."""

from orchestrator.security.identity import IdentityContextError, Principal
from orchestrator.settings import get_settings

class ProductionIdentityResolver:
    def __init__(self, allow_anonymous: bool | None = None) -> None:
        if allow_anonymous is None:
            allow_anonymous = get_settings().allow_anonymous
        self.allow_anonymous = allow_anonymous

    def resolve(self, user_id: str | None, tenant_id: str | None, roles: list[str] | None = None) -> Principal | None:
        if user_id and tenant_id:
            return Principal(user_id=user_id, tenant_id=tenant_id, roles=tuple(roles or ["operator"]))
        if self.allow_anonymous:
            return None
        raise IdentityContextError("Authenticated user and tenant claims are required")
