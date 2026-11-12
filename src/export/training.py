"""Optional, non-blocking export of caller-approved training examples."""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any

from src.core.security.audit import redact
from src.export.formatters import format_openai_chat_jsonl
from src.export.huggingface import HuggingFaceSync


logger = logging.getLogger(__name__)
_STOP = object()


class TrainingDataExporter:
    """Append completed prompt/response pairs to daily OpenAI JSONL files."""

    def __init__(
        self,
        enabled: bool = False,
        output_dir: str | Path = "logs/training-export",
        max_queue_size: int = 1000,
        flush_interval: float = 5.0,
        huggingface_sync: HuggingFaceSync | None = None,
    ) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be positive")
        if flush_interval <= 0:
            raise ValueError("flush_interval must be positive")
        self.enabled = enabled
        self.output_dir = Path(output_dir)
        self._queue: asyncio.Queue[dict[str, Any] | object] = asyncio.Queue(maxsize=max_queue_size)
        self._flush_interval = flush_interval
        self._worker_task: asyncio.Task[None] | None = None
        self._closing = False
        self._huggingface_sync = huggingface_sync

        if self.enabled and os.getenv("FORGE_HF_SYNC_ENABLED", "false").lower() == "true":
            try:
                self._huggingface_sync = self._huggingface_sync or HuggingFaceSync(
                    token=os.getenv("FORGE_HF_TOKEN", ""),
                    repo_id=os.getenv("FORGE_HF_REPO_ID", ""),
                    repo_type=os.getenv("FORGE_HF_REPO_TYPE", "dataset"),
                )
            except Exception:
                logger.exception("Hugging Face sync is unavailable; local training export remains enabled")

    @classmethod
    def from_environment(cls) -> "TrainingDataExporter":
        return cls(
            enabled=os.getenv("FORGE_TRAINING_EXPORT_ENABLED", "false").lower() == "true",
            output_dir=os.getenv("FORGE_TRAINING_EXPORT_DIR", "logs/training-export"),
        )

    def record(self, prompt: str, final_response: str, metadata: dict[str, Any] | None = None) -> None:
        if not self.enabled or self._closing:
            return
        try:
            safe_metadata = redact(metadata or {})
            record = {
                "prompt": prompt,
                "final_response": final_response,
                "metadata": safe_metadata,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }
            loop = asyncio.get_running_loop()
            if self._worker_task is None:
                self._worker_task = loop.create_task(self._drain_loop())
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            logger.warning(
                "Training export queue full; dropping record for run %s",
                (metadata or {}).get("run_id", "unknown"),
            )
        except Exception:
            logger.exception("Training export record could not be queued")

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
            logger.exception("Training export flush failed; batch dropped")
            return
        if self._huggingface_sync is not None:
            try:
                await asyncio.to_thread(
                    self._huggingface_sync.push,
                    path,
                    path.name,
                )
            except Exception:
                logger.exception("Hugging Face upload failed; local training file retained")

    def _write_batch(self, batch: list[dict[str, Any]]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        date_string = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.output_dir / f"training-{date_string}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            for record in batch:
                line = format_openai_chat_jsonl(record["prompt"], record["final_response"])
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
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
