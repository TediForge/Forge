import asyncio

from orchestrator.computer.config import ComputerConfig
from orchestrator.computer.manager import ComputerManager


class _FakeInstance:
    def __init__(self, instance_id: str) -> None:
        self.instance_id = instance_id
        self.destroyed = False

    async def destroy(self) -> None:
        self.destroyed = True


class _FakeDriver:
    def __init__(self) -> None:
        self.instances: list[_FakeInstance] = []

    async def boot(self) -> _FakeInstance:
        instance = _FakeInstance(f"vm-{len(self.instances) + 1}")
        self.instances.append(instance)
        return instance


class _RecordingAuditLog:
    def __init__(self) -> None:
        self.events = []

    def record(self, event, run_id, tenant_id, user_id, **details):
        self.events.append({
            "event": event,
            "run_id": run_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "details": details,
        })


def test_concurrent_users_receive_distinct_computers_and_all_vms_are_destroyed(monkeypatch):
    async def run() -> None:
        monkeypatch.setattr(
            "orchestrator.computer.manager._host_instance_limit",
            lambda configured_limit, memory_mb: configured_limit,
        )
        driver = _FakeDriver()
        audit_log = _RecordingAuditLog()
        manager = ComputerManager(
            ComputerConfig(min_warm=0, max_pool_size=50),
            driver=driver,
            audit_log=audit_log,
        )
        requests = [
            (user_index, request_index)
            for user_index in range(10)
            for request_index in range(5)
        ]
        leases = await asyncio.gather(*(
            manager.acquire(
                f'["tenant-{user_index}","user-{user_index}","run-{request_index}"]',
                tenant_id=f"tenant-{user_index}",
                user_id=f"user-{user_index}",
                run_id=f"run-{request_index}",
            )
            for user_index, request_index in requests
        ))

        assert len({instance.instance_id for instance in leases}) == len(requests)
        await asyncio.gather(*(
            manager.release(
                instance,
                f'["tenant-{user_index}","user-{user_index}","run-{request_index}"]',
            )
            for instance, (user_index, request_index) in zip(leases, requests)
        ))
        await asyncio.gather(*(
            manager.close_session(
                f'["tenant-{user_index}","user-{user_index}","run-{request_index}"]'
            )
            for user_index, request_index in requests
        ))

        assert len(driver.instances) == len(requests)
        assert all(instance.destroyed for instance in driver.instances)
        assert not manager._instances
        created = [event for event in audit_log.events if event["event"] == "computer.vm.created"]
        destroyed = [event for event in audit_log.events if event["event"] == "computer.vm.destroyed"]
        assert len(created) == len(destroyed) == len(requests)
        assert {
            (event["tenant_id"], event["user_id"], event["run_id"])
            for event in created
        } == {
            (f"tenant-{user_index}", f"user-{user_index}", f"run-{request_index}")
            for user_index, request_index in requests
        }

        await manager.close()

    asyncio.run(run())
