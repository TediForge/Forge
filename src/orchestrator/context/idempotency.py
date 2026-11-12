"""Request-level idempotency for orchestration writes."""

import threading
import time
from typing import Any


class IdempotencyStore:
    def __init__(self, ttl_seconds: int = 86400) -> None:
        self.ttl_seconds = ttl_seconds
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def begin(self, tenant_id: str, user_id: str, key: str, request_fingerprint: str) -> tuple[str, dict[str, Any] | None]:
        composite = f"{tenant_id}:{user_id}:{key}"
        with self._lock:
            now = time.monotonic()
            record = self._records.get(composite)
            if record and record["expiresAt"] <= now:
                self._records.pop(composite, None)
                record = None
            if record and record["fingerprint"] != request_fingerprint:
                return "conflict", record
            if record:
                return "replay", record
            self._records[composite] = {"fingerprint": request_fingerprint, "expiresAt": now + self.ttl_seconds, "status": "inProgress"}
            return "started", None

    def complete(self, tenant_id: str, user_id: str, key: str, response: dict[str, Any]) -> None:
        composite = f"{tenant_id}:{user_id}:{key}"
        with self._lock:
            record = self._records.get(composite)
            if record:
                record.update({"status": "completed", "response": response})

    def get(self, tenant_id: str, user_id: str, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._records.get(f"{tenant_id}:{user_id}:{key}")
