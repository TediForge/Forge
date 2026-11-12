"""Role and resource authorization for Forge."""

from dataclasses import dataclass
from enum import Enum

from src.core.security.identity import Principal


class Permission(str, Enum):
    RUN = "orchestrate:run"
    READ_SESSION = "session:read"
    MANAGE_TENANT = "tenant:manage"
    MANAGE_INTEGRATIONS = "integration:manage"
    USE_INTEGRATION = "integration:use"
    ADMIN = "admin:*"


ROLE_PERMISSIONS = {
    "viewer": {Permission.READ_SESSION},
    "operator": {Permission.RUN, Permission.READ_SESSION, Permission.USE_INTEGRATION},
    "integration_admin": {Permission.RUN, Permission.READ_SESSION, Permission.USE_INTEGRATION, Permission.MANAGE_INTEGRATIONS},
    "admin": set(Permission),
}


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    tenant_id: str


class AuthorizationError(PermissionError):
    pass


def authorize(principal: Principal, permission: Permission, resource_tenant_id: str | None = None) -> AuthorizationDecision:
    tenant_id = resource_tenant_id or principal.tenant_id
    if tenant_id != principal.tenant_id:
        return AuthorizationDecision(False, "Cross-tenant access denied", tenant_id)
    granted = set()
    for role in principal.roles:
        granted.update(ROLE_PERMISSIONS.get(role.lower(), set()))
    if Permission.ADMIN in granted or permission in granted:
        return AuthorizationDecision(True, "Authorized", tenant_id)
    return AuthorizationDecision(False, f"Missing permission: {permission.value}", tenant_id)


def require_authorization(principal: Principal, permission: Permission, resource_tenant_id: str | None = None) -> None:
    decision = authorize(principal, permission, resource_tenant_id)
    if not decision.allowed:
        raise AuthorizationError(decision.reason)
