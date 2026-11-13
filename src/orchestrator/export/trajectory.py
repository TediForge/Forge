"""Optional, bounded trajectory export for evaluation and future offline tuning."""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any

from orchestrator.security.audit import redact
from orchestrator.export.formatters import format_openai_chat_jsonl
from orchestrator.export.huggingface import HuggingFaceSync
from orchestrator.settings import DEFAULT_TRAJECTORY_EXPORT_DIR, get_settings


logger = logging.getLogger(__name__)
_STOP = object()
MAX_RECORD_BYTES = 128 * 1024
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)\+?\d[\d ().-]{7,}\d(?!\w)")
_SECRET_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "refreshtoken",
    "secret",
    "token",
}
_PAYLOAD_KEYS = {
    "audiobytes",
    "base64",
    "blob",
    "bytes",
    "filedata",
    "imagebytes",
    "mediadata",
}


class TrajectoryExporter:
    """Append explicitly opted-in, redacted and versioned run records."""

    def __init__(
        self,
        enabled: bool = False,
        output_dir: str | Path = DEFAULT_TRAJECTORY_EXPORT_DIR,
        max_queue_size: int = 1000,
        flush_interval: float = 5.0,
        huggingface_sync: HuggingFaceSync | None = None,
        max_record_bytes: int = MAX_RECORD_BYTES,
    ) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be positive")
        if flush_interval <= 0:
            raise ValueError("flush_interval must be positive")
        if max_record_bytes < 1:
            raise ValueError("max_record_bytes must be positive")
        self.enabled = enabled
        self.output_dir = Path(output_dir)
        self._queue: asyncio.Queue[dict[str, Any] | object] = asyncio.Queue(maxsize=max_queue_size)
        self._flush_interval = flush_interval
        self._max_record_bytes = max_record_bytes
        self._worker_task: asyncio.Task[None] | None = None
        self._closing = False
        self._huggingface_sync = huggingface_sync

        settings = get_settings()
        token = settings.hf_token
        token_value = token.get_secret_value() if token is not None else ""
        if settings.hf_repo_id and not token_value:
            raise ValueError("HF_TOKEN is required when FORGE_HF_REPO_ID is configured")
        if self.enabled and settings.hf_repo_id:
            self._huggingface_sync = self._huggingface_sync or HuggingFaceSync(
                token=token_value,
                repo_id=settings.hf_repo_id,
            )

    @classmethod
    def from_environment(cls) -> "TrajectoryExporter":
        return cls(
            enabled=True,
            output_dir=DEFAULT_TRAJECTORY_EXPORT_DIR,
        )

    def record(
        self,
        prompt: str,
        final_response: str,
        metadata: dict[str, Any] | None = None,
        *,
        steps: list[dict[str, Any]] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        outcome: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled or self._closing:
            return
        try:
            safe_metadata = _redact_export_value(metadata or {})
            record = {
                "schemaVersion": "1.0",
                "purpose": "evaluation",
                "runId": safe_metadata.get("run_id"),
                "messages": format_openai_chat_jsonl(
                    _redact_export_text(prompt),
                    _redact_export_text(final_response),
                )["messages"],
                "steps": _redact_export_value(steps or []),
                "toolCalls": _redact_export_value(tool_calls or []),
                "outcome": _redact_export_value(outcome or {"status": "completed"}),
                "metadata": safe_metadata,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }
            if "grade" in safe_metadata:
                record["grade"] = safe_metadata["grade"]
            serialized = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            if len(serialized.encode("utf-8")) > self._max_record_bytes:
                logger.warning(
                    "Trajectory export record exceeded %s bytes and was dropped",
                    self._max_record_bytes,
                )
                return
            loop = asyncio.get_running_loop()
            if self._worker_task is None:
                self._worker_task = loop.create_task(self._drain_loop())
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            logger.warning(
                "Trajectory export queue full; dropping record for run %s",
                (metadata or {}).get("run_id", "unknown"),
            )
        except Exception:
            logger.exception("Trajectory export record could not be queued")

    async def _drain_loop(self) -> None:
        batch: list[dict[str, Any]] = []
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=self._flush_interval)
            except asyncio.TimeoutError:
                if batch:
                    await self._flush_and_ack(batch)
                    batch = []
                continue
            if item is _STOP:
                if batch:
                    await self._flush_and_ack(batch)
                self._queue.task_done()
                return
            if not isinstance(item, dict):
                self._queue.task_done()
                continue
            batch.append(item)
            if len(batch) >= 10:
                await self._flush_and_ack(batch)
                batch = []

    async def _flush_and_ack(self, batch: list[dict[str, Any]]) -> None:
        try:
            await self._flush(batch)
        finally:
            for _ in batch:
                self._queue.task_done()

    async def _flush(self, batch: list[dict[str, Any]]) -> None:
        try:
            path = await asyncio.to_thread(self._write_batch, batch)
        except Exception:
            logger.exception("Trajectory export flush failed; batch dropped")
            return
        if self._huggingface_sync is not None:
            try:
                await asyncio.to_thread(
                    self._huggingface_sync.push,
                    path,
                    path.name,
                )
            except Exception:
                logger.exception("Hugging Face upload failed; local trajectory file retained")

    def _write_batch(self, batch: list[dict[str, Any]]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        date_string = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.output_dir / f"trajectory-{date_string}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            for record in batch:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return path

    async def shutdown(self) -> None:
        if self._worker_task is None:
            self._closing = True
            return
        if self._closing:
            await self._worker_task
            return
        self._closing = True
        await self._queue.put(_STOP)
        await self._worker_task
        self._worker_task = None


def _redact_export_text(value: str) -> str:
    redacted = redact(value)
    return _PHONE.sub("[REDACTED_PHONE]", _EMAIL.sub("[REDACTED_EMAIL]", redacted))


def _redact_export_value(value: Any) -> Any:
    value = redact(value)
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).casefold().replace("-", "").replace("_", "")
            if normalized_key in _SECRET_KEYS:
                safe[key] = "[REDACTED]"
            elif normalized_key in _PAYLOAD_KEYS:
                safe[key] = "[OMITTED]"
            else:
                safe[key] = _redact_export_value(item)
        return safe
    if isinstance(value, list):
        return [_redact_export_value(item) for item in value]
    if isinstance(value, str):
        return _redact_export_text(value)
    return value
