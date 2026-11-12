"""Redacted structured audit event sink."""

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.settings import get_settings


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
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or get_settings().audit_log_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    def record(self, event: str, run_id: str, tenant_id: str, user_id: str, **details: Any) -> dict[str, Any]:
        entry = {
            "event": event,
            "runId": run_id,
            "tenantId": tenant_id,
            "userId": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": redact(details),
        }
        serialized = json.dumps(entry, ensure_ascii=True, sort_keys=True) + "\n"
        with self._write_lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
        return entry
