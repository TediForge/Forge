import asyncio

import pytest

from orchestrator.computer.config import ComputerConfig
from orchestrator.computer.errors import ComputerPolicyError, ComputerUnavailableError
from orchestrator.computer.manager import ComputerManager
from orchestrator.computer.policy import PolicyEngine
from orchestrator.tools.executor import ToolExecutor


def test_policy_rejects_destructive_commands_and_non_workspace_paths():
    policy = PolicyEngine()

    with pytest.raises(ComputerPolicyError):
        policy.validate_command("rm -rf /")
    with pytest.raises(ComputerPolicyError):
        policy.validate_command("shutdown now")
    with pytest.raises(ComputerPolicyError):
        policy.validate_path("../etc/passwd")
    with pytest.raises(ComputerPolicyError):
        policy.validate_path("/etc/passwd")
    assert policy.validate_path("outputs/result.txt") == "outputs/result.txt"


class _FakeInstance:
    def __init__(self, instance_id):
        self.instance_id = instance_id
        self.destroyed = False

    async def execute(self, command):
        return f"guest:{command}"

    async def execute_result(self, command):
        return {
            "output": f"guest:{command}",
            "exit_code": 0,
            "timed_out": False,
            "truncated": False,
        }

    async def read_file(self, path):
        return b"guest file"

    async def write_file(self, path, content):
        self.written = (path, content)

    async def destroy(self):
        self.destroyed = True


class _FakeDriver:
    def __init__(self):
        self.boot_count = 0

    async def boot(self):
        self.boot_count += 1
        return _FakeInstance(f"vm-{self.boot_count}")


def test_manager_caps_instances_and_replaces_vm_after_release():
    async def run():
        driver = _FakeDriver()
        manager = ComputerManager(
            ComputerConfig(pool_size=1, max_instances=1),
            driver=driver,
        )
        first = await manager.acquire()
        waiting = asyncio.create_task(manager.acquire())
        await asyncio.sleep(0)
        assert not waiting.done()

        await manager.release(first)
        second = await asyncio.wait_for(waiting, timeout=1)
        assert first.destroyed
        assert second.instance_id == "vm-2"
        assert driver.boot_count == 2
        await manager.release(second)
        await manager.close()

    asyncio.run(run())


def test_manager_keeps_a_guest_for_one_run_and_closes_it_at_run_end():
    async def run():
        driver = _FakeDriver()
        manager = ComputerManager(
            ComputerConfig(pool_size=1, max_instances=1),
            driver=driver,
        )
        first = await manager.acquire("run-1")
        await manager.release(first, "run-1")
        second = await manager.acquire("run-1")
        assert second is first
        assert not first.destroyed
        await manager.release(second, "run-1")
        await manager.close_session("run-1")
        assert first.destroyed
        await manager.close()

    asyncio.run(run())


def test_manager_serializes_operations_within_a_run():
    async def run():
        driver = _FakeDriver()
        manager = ComputerManager(
            ComputerConfig(min_warm=0, max_pool_size=2, acquire_timeout_seconds=1),
            driver=driver,
        )
        first = await manager.acquire("run-1")
        waiting = asyncio.create_task(manager.acquire("run-1"))
        await asyncio.sleep(0)
        assert not waiting.done()
        await manager.release(first, "run-1")
        second = await asyncio.wait_for(waiting, timeout=1)
        assert second is first
        assert driver.boot_count == 1
        await manager.release(second, "run-1")
        await manager.close_session("run-1")
        await manager.close()

    asyncio.run(run())


def test_manager_queues_same_run_requests_and_scales_for_distinct_runs(monkeypatch):
    async def run():
        monkeypatch.setattr(
            "orchestrator.computer.manager._host_instance_limit",
            lambda configured_limit, memory_mb: configured_limit,
        )
        driver = _FakeDriver()
        manager = ComputerManager(
            ComputerConfig(min_warm=0, max_pool_size=50, acquire_timeout_seconds=1),
            driver=driver,
        )
        leases = await asyncio.gather(*(
            manager.acquire(
                f'["tenant-{index % 10}","user-{index % 10}","run-{index}"]',
                tenant_id=f"tenant-{index % 10}",
                user_id=f"user-{index % 10}",
                run_id=f"run-{index}",
            )
            for index in range(50)
        ))

        assert len({instance.instance_id for instance in leases}) == 50
        assert driver.boot_count == 50
        await asyncio.gather(*(
            manager.release(instance, f'["tenant-{index % 10}","user-{index % 10}","run-{index}"]')
            for index, instance in enumerate(leases)
        ))
        await manager.close()

    asyncio.run(run())


def test_manager_times_out_when_capacity_is_exhausted():
    async def run():
        manager = ComputerManager(
            ComputerConfig(
                min_warm=1,
                max_pool_size=1,
                acquire_timeout_seconds=0.01,
            ),
            driver=_FakeDriver(),
        )
        first = await manager.acquire()
        with pytest.raises(ComputerUnavailableError, match="Timed out"):
            await manager.acquire()
        await manager.release(first)
        await manager.close()

    asyncio.run(run())


def test_manager_replenishes_warm_pool_below_scale_threshold():
    async def run():
        driver = _FakeDriver()
        manager = ComputerManager(
            ComputerConfig(min_warm=1, max_pool_size=3, scale_threshold=0.2),
            driver=driver,
        )
        leased = await manager.acquire()
        await asyncio.sleep(0.01)

        assert manager._available.qsize() == 1
        assert driver.boot_count == 2
        await manager.release(leased)
        await manager.close()

    asyncio.run(run())


def test_computer_tool_uses_manager_and_releases_vm():
    class FakeManager:
        def __init__(self):
            self.instance = _FakeInstance("vm")
            self.released = []

        async def acquire(self, session_id=None, **identity):
            return self.instance

        async def release(self, instance, session_id=None, **options):
            self.released.append((instance, options))

        async def close(self):
            return None

    async def run():
        manager = FakeManager()
        executor = ToolExecutor(computerManager=manager)
        result = await executor.executeAsync({
            "function": {
                "name": "computer",
                "arguments": {"operation": "execute", "command": "printf ok"},
            },
        })
        assert result["success"] is True
        assert result["output"] == "guest:printf ok"
        assert result["exit_code"] == 0
        assert manager.released == [(manager.instance, {})]
        await executor.close()

    asyncio.run(run())


def test_computer_sessions_are_isolated_by_tenant_and_user():
    async def run():
        driver = _FakeDriver()
        manager = ComputerManager(
            ComputerConfig(pool_size=0, max_instances=2),
            driver=driver,
        )
        executor = ToolExecutor(computerManager=manager)
        tool_call = {
            "function": {
                "name": "computer",
                "arguments": {"operation": "execute", "command": "printf ok"},
            },
        }

        for tenant_id in ("tenant-a", "tenant-b"):
            result = await executor.executeAsync(
                tool_call,
                context={
                    "tenant_id": tenant_id,
                    "user_id": "user-1",
                    "run_id": "run-shared",
                },
            )
            assert result["success"] is True

        assert driver.boot_count == 2
        await executor.closeComputerSession(
            "run-shared", tenant_id="tenant-a", user_id="user-1"
        )
        await executor.closeComputerSession(
            "run-shared", tenant_id="tenant-b", user_id="user-1"
        )
        await executor.close()

    asyncio.run(run())


def test_computer_tool_rejects_policy_violation_before_acquiring():
    class FakeManager:
        def __init__(self):
            self.acquire_count = 0

        async def acquire(self, session_id=None, **identity):
            self.acquire_count += 1
            raise AssertionError("policy must run before acquisition")

        async def close(self):
            return None

    async def run():
        manager = FakeManager()
        executor = ToolExecutor(computerManager=manager)
        result = await executor.executeAsync({
            "function": {
                "name": "computer",
                "arguments": {"operation": "execute", "command": "rm -rf /"},
            },
        })
        assert result["success"] is False
        assert result["errorCode"] == "POLICY_VIOLATION"
        assert manager.acquire_count == 0
        await executor.close()

    asyncio.run(run())


def test_computer_tool_destroys_session_when_cancelled():
    class BlockingInstance(_FakeInstance):
        async def execute_result(self, command):
            await asyncio.Event().wait()

    class FakeManager:
        def __init__(self):
            self.instance = BlockingInstance("vm")
            self.release_options = []

        async def acquire(self, session_id=None, **identity):
            return self.instance

        async def release(self, instance, session_id=None, **options):
            self.release_options.append(options)

        async def close(self):
            return None

    async def run():
        manager = FakeManager()
        executor = ToolExecutor(computerManager=manager)
        task = asyncio.create_task(executor.executeAsync({
            "function": {
                "name": "computer",
                "arguments": {"operation": "execute", "command": "sleep 10"},
            },
        }, context={
            "tenant_id": "tenant",
            "user_id": "user",
            "run_id": "run",
        }))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert manager.release_options == [{"destroy_session": True}]

    asyncio.run(run())


def test_computer_tool_returns_unavailable_when_runtime_is_missing():
    async def run():
        executor = ToolExecutor()
        result = await executor.executeAsync({
            "function": {
                "name": "computer",
                "arguments": {"operation": "execute", "command": "echo hello"},
            },
        })
        assert result["success"] is False
        assert result["errorCode"] == "COMPUTER_UNAVAILABLE"
        await executor.close()

    asyncio.run(run())
