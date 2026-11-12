import asyncio
import json

from src.export.training import TrainingDataExporter


def test_disabled_exporter_is_noop(tmp_path):
    exporter = TrainingDataExporter(output_dir=tmp_path)
    exporter.record("prompt", "answer")
    assert exporter._worker_task is None
    assert list(tmp_path.iterdir()) == []


def test_enabled_exporter_flushes_jsonl_on_shutdown(tmp_path):
    async def scenario():
        exporter = TrainingDataExporter(enabled=True, output_dir=tmp_path)
        exporter.record("prompt", "answer")
        await exporter.shutdown()
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        record = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
        assert record == {
            "messages": [
                {"role": "user", "content": "prompt"},
                {"role": "assistant", "content": "answer"},
            ]
        }

    asyncio.run(scenario())


def test_metadata_is_redacted_before_it_enters_queue(tmp_path):
    async def scenario():
        exporter = TrainingDataExporter(enabled=True, output_dir=tmp_path)
        exporter.record("prompt", "answer", {"api_key": "secret", "run_id": "run-1"})
        record = exporter._queue.get_nowait()
        assert record["metadata"] == {"api_key": "[REDACTED]", "run_id": "run-1"}
        exporter._queue.task_done()
        await exporter.shutdown()

    asyncio.run(scenario())


def test_full_queue_drops_record_without_raising(tmp_path):
    async def scenario():
        exporter = TrainingDataExporter(enabled=True, output_dir=tmp_path, max_queue_size=1)
        exporter.record("first", "answer")
        exporter.record("dropped", "answer")
        assert exporter._queue.qsize() == 1
        await exporter.shutdown()

    asyncio.run(scenario())


def test_shutdown_flushes_all_pending_records(tmp_path):
    async def scenario():
        exporter = TrainingDataExporter(enabled=True, output_dir=tmp_path)
        for index in range(3):
            exporter.record(f"prompt-{index}", f"answer-{index}")
        await exporter.shutdown()
        path = next(tmp_path.glob("*.jsonl"))
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 3

    asyncio.run(scenario())


def test_huggingface_upload_failure_does_not_drop_local_jsonl(tmp_path):
    class FakeSync:
        def __init__(self):
            self.uploaded = []

        def push(self, local_path, path_in_repo):
            self.uploaded.append((local_path, path_in_repo))
            raise RuntimeError("offline")

    async def scenario():
        sync = FakeSync()
        exporter = TrainingDataExporter(
            enabled=True,
            output_dir=tmp_path,
            huggingface_sync=sync,
        )
        exporter.record("prompt", "answer")
        await exporter.shutdown()
        assert len(sync.uploaded) == 1
        assert list(tmp_path.glob("*.jsonl"))

    asyncio.run(scenario())
