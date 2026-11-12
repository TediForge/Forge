"""Redacted structured audit event sink."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REDACTION_KEYS = {
    "token", "accesstoken", "refresh_token", "refreshtoken", "api_key", "apikey",
    "authorization", "password", "secret", "cookie",
}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in REDACTION_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(?i)(bearer\s+)\S+", r"\1[REDACTED]", value)
    return value


class AuditLog:
    def __init__(self, path: str | Path = "logs/forge-audit.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, run_id: str, tenant_id: str, user_id: str, **details: Any) -> dict[str, Any]:
        entry = {
            "event": event,
            "runId": run_id,
            "tenantId": tenant_id,
            "userId": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": redact(details),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True, sort_keys=True) + "\n")
        return entry
