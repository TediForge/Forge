"""Tenant-bound authenticated principal context."""

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    roles: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    attributes: dict[str, str] = field(default_factory=dict)

    def has_role(self, *roles: str) -> bool:
        return bool(set(self.roles).intersection(roles))


class IdentityContextError(PermissionError):
    pass


def require_principal(user_id: str | None, tenant_id: str | None, roles: Iterable[str] = ()) -> Principal:
    if not user_id:
        raise IdentityContextError("Authenticated user identity is required")
    if not tenant_id:
        raise IdentityContextError("Authenticated tenant identity is required")
    return Principal(user_id=user_id, tenant_id=tenant_id, roles=tuple(roles))
