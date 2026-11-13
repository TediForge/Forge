"""Memory-aware, asynchronously scaling pool of Firecracker microVMs."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from orchestrator.computer.config import ComputerConfig, DEFAULT_COMPUTER_CONFIG
from orchestrator.computer.errors import ComputerError, ComputerUnavailableError
from orchestrator.computer.hypervisor import FirecrackerDriver
from orchestrator.computer.instance import ComputerInstance


logger = logging.getLogger(__name__)
_SYSTEM_IDENTITY = ("system", "system", "system")
_HOST_MEMORY_RESERVE_MB = 512
_HOST_MEMORY_FRACTION = 0.8


def _host_instance_limit(configured_limit: int, memory_mb: int) -> int:
    sysconf = getattr(os, "sysconf", None)
    if not callable(sysconf):
        return configured_limit
    try:
        page_size = sysconf("SC_PAGE_SIZE")
        page_count = sysconf("SC_PHYS_PAGES")
        host_memory_mb = page_size * page_count // (1024 * 1024)
        cgroup_limit = _read_cgroup_memory_limit_mb()
        if cgroup_limit is not None:
            host_memory_mb = min(host_memory_mb, cgroup_limit)
        usable_memory_mb = int(host_memory_mb * _HOST_MEMORY_FRACTION) - _HOST_MEMORY_RESERVE_MB
        return min(configured_limit, max(0, usable_memory_mb // memory_mb))
    except (OSError, ValueError, TypeError):
        logger.exception("Could not determine host memory limit; using configured computer limit")
        return configured_limit


def _read_cgroup_memory_limit_mb() -> int | None:
    for path in (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ):
        try:
            raw_limit = path.read_text(encoding="ascii").strip()
        except OSError:
            continue
        if raw_limit == "max":
            return None
        try:
            limit_mb = int(raw_limit) // (1024 * 1024)
        except ValueError:
            logger.warning("Ignoring invalid cgroup memory limit at %s", path)
            continue
        if limit_mb > 1 << 40:
            return None
        return limit_mb
    return None


class ComputerManager:
    def __init__(
        self,
        config: ComputerConfig = DEFAULT_COMPUTER_CONFIG,
        driver: FirecrackerDriver | None = None,
        audit_log: Any | None = None,
    ) -> None:
        self.config = config
        self.driver = driver or FirecrackerDriver(config)
        self.audit_log = audit_log
        self._instance_limit = _host_instance_limit(config.instance_limit, config.memory_mb)
        self._available: asyncio.Queue[ComputerInstance | None] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._startup_lock = asyncio.Lock()
        self._instances: dict[str, ComputerInstance] = {}
        self._leased: set[str] = set()
        self._sessions: dict[str, str] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._closed_sessions: set[str] = set()
        self._identities: dict[str, tuple[str, str, str]] = {}
        self._created_audited: set[str] = set()
        self._booting = 0
        self._started = False
        self._closed = False
        self._replenish_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        async with self._startup_lock:
            if self._started:
                return
            if self._closed:
                raise ComputerError("Computer manager is closed")
            self._started = True
            warm_count = min(self.config.warm_pool_size, self._instance_limit)
            instances = []
            try:
                for _ in range(warm_count):
                    instances.append(await self._boot_reserved(identity=_SYSTEM_IDENTITY))
            except BaseException:
                self._started = False
                results = await asyncio.gather(
                    *(self._destroy_instance(instance) for instance in instances),
                    return_exceptions=True,
                )
                failures = [result for result in results if isinstance(result, BaseException)]
                if failures:
                    raise BaseExceptionGroup("Computer pool startup cleanup failed", failures)
                raise
            for instance in instances:
                await self._publish(instance)

    async def acquire(
        self,
        session_id: str | None = None,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        run_id: str | None = None,
    ) -> ComputerInstance:
        await self.start()
        identity = self._identity(tenant_id, user_id, run_id)
        if session_id is None:
            return await self._acquire_instance(identity)

        async with self._lock:
            if self._closed:
                raise ComputerError("Computer manager is closed")
            if session_id in self._closed_sessions:
                raise ComputerError("Computer session is closed")
            session_lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        try:
            await asyncio.wait_for(
                session_lock.acquire(),
                timeout=self.config.acquire_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ComputerUnavailableError("Timed out waiting for the computer session") from exc

        try:
            async with self._lock:
                if session_id in self._closed_sessions:
                    raise ComputerError("Computer session is closed")
                instance_id = self._sessions.get(session_id)
                instance = self._instances.get(instance_id) if instance_id is not None else None
                if instance is not None:
                    self._leased.add(instance.instance_id)
                    self._identities[instance.instance_id] = identity
                    return instance
                self._sessions.pop(session_id, None)

            instance = await self._acquire_instance(identity)
            async with self._lock:
                if self._closed:
                    should_destroy = True
                else:
                    self._sessions[session_id] = instance.instance_id
                    should_destroy = False
            if should_destroy:
                await self._destroy_instance(instance)
                raise ComputerError("Computer manager is closed")
            return instance
        except BaseException:
            if session_lock.locked():
                session_lock.release()
            raise

    async def _acquire_instance(self, identity: tuple[str, str, str]) -> ComputerInstance:
        while True:
            if self._closed:
                raise ComputerError("Computer manager is closed")
            try:
                instance = self._available.get_nowait()
            except asyncio.QueueEmpty:
                instance = None
            if instance is not None:
                async with self._lock:
                    if self._closed:
                        should_destroy = True
                    else:
                        self._leased.add(instance.instance_id)
                        self._identities[instance.instance_id] = identity
                        should_destroy = False
                if should_destroy:
                    await self._destroy_instance(instance)
                    raise ComputerError("Computer manager is closed")
                if self._available.qsize() / max(1, self.config.warm_pool_size) <= self.config.scale_threshold:
                    self._schedule_replenish()
                return instance

            async with self._lock:
                can_boot = len(self._instances) + self._booting < self._instance_limit
                if can_boot:
                    self._booting += 1
            if can_boot:
                instance = await self._boot_reserved(reserved=True, identity=identity)
                async with self._lock:
                    if self._closed:
                        should_destroy = True
                    else:
                        self._leased.add(instance.instance_id)
                        self._identities[instance.instance_id] = identity
                        should_destroy = False
                if should_destroy:
                    await self._destroy_instance(instance)
                    raise ComputerError("Computer manager is closed")
                return instance

            try:
                instance = await asyncio.wait_for(
                    self._available.get(),
                    timeout=self.config.acquire_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise ComputerUnavailableError("Timed out waiting for computer capacity") from exc
            if instance is None:
                raise ComputerError("Computer manager is closed")
            async with self._lock:
                if self._closed:
                    should_destroy = True
                else:
                    self._leased.add(instance.instance_id)
                    self._identities[instance.instance_id] = identity
                    should_destroy = False
            if should_destroy:
                await self._destroy_instance(instance)
                raise ComputerError("Computer manager is closed")
            return instance

    async def release(
        self,
        instance: ComputerInstance,
        session_id: str | None = None,
        *,
        destroy_session: bool = False,
    ) -> None:
        session_lock = None
        destroy = session_id is None or destroy_session
        async with self._lock:
            if instance.instance_id not in self._leased:
                raise ComputerError("Computer instance is not leased by this manager")
            if session_id is not None:
                if self._sessions.get(session_id) != instance.instance_id:
                    raise ComputerError("Computer instance does not belong to this session")
                session_lock = self._session_locks.get(session_id)
                if destroy:
                    self._sessions.pop(session_id, None)
                    self._closed_sessions.add(session_id)
                    self._instances.pop(instance.instance_id, None)
            self._leased.remove(instance.instance_id)
            if not destroy:
                if session_lock is not None and session_lock.locked():
                    session_lock.release()
                return
            self._instances.pop(instance.instance_id, None)

        try:
            await self._destroy_instance(instance)
        finally:
            if session_lock is not None and session_lock.locked():
                session_lock.release()
            if not self._closed:
                self._schedule_replenish()

    async def close_session(self, session_id: str) -> None:
        async with self._lock:
            session_lock = self._session_locks.get(session_id)
            if session_lock is None:
                self._closed_sessions.add(session_id)
                return
            self._closed_sessions.add(session_id)
        try:
            await asyncio.wait_for(
                session_lock.acquire(),
                timeout=self.config.acquire_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ComputerError("Timed out waiting to close the computer session") from exc

        try:
            async with self._lock:
                instance_id = self._sessions.pop(session_id, None)
                self._session_locks.pop(session_id, None)
                if instance_id is None:
                    return
                if instance_id in self._leased:
                    self._sessions[session_id] = instance_id
                    raise ComputerError("Cannot close a computer session with an active operation")
                instance = self._instances.pop(instance_id, None)
            if instance is not None:
                await self._destroy_instance(instance)
        finally:
            if session_lock.locked():
                session_lock.release()
            if not self._closed:
                self._schedule_replenish()

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            instances = list(self._instances.values())
            self._instances.clear()
            self._leased.clear()
            self._sessions.clear()
            self._session_locks.clear()
            self._closed_sessions.clear()
            for _ in range(self._instance_limit + 1):
                self._available.put_nowait(None)
        if self._replenish_task is not None:
            await asyncio.gather(self._replenish_task, return_exceptions=True)
        results = await asyncio.gather(
            *(self._destroy_instance(instance) for instance in instances),
            return_exceptions=True,
        )
        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            raise BaseExceptionGroup("Computer instances failed to shut down", failures)

    async def _boot_reserved(
        self,
        *,
        reserved: bool = False,
        identity: tuple[str, str, str] = _SYSTEM_IDENTITY,
    ) -> ComputerInstance:
        if not reserved:
            async with self._lock:
                if self._closed:
                    raise ComputerError("Computer manager is closed")
                if len(self._instances) + self._booting >= self._instance_limit:
                    raise ComputerError("Computer instance capacity is exhausted")
                self._booting += 1
        try:
            instance = await self.driver.boot()
        except asyncio.CancelledError:
            async with self._lock:
                self._booting -= 1
            raise
        except ComputerUnavailableError:
            async with self._lock:
                self._booting -= 1
            raise
        except (OSError, RuntimeError, asyncio.TimeoutError) as exc:
            async with self._lock:
                self._booting -= 1
            raise ComputerUnavailableError("Computer instance could not be started") from exc
        async with self._lock:
            self._booting -= 1
            if self._closed:
                should_destroy = True
            else:
                self._instances[instance.instance_id] = instance
                self._identities[instance.instance_id] = identity
                should_destroy = False
        if should_destroy:
            await self._destroy_instance(instance)
            raise ComputerError("Computer manager is closed")
        try:
            self._record_lifecycle("computer.vm.created", instance)
            self._created_audited.add(instance.instance_id)
        except Exception as audit_error:
            try:
                await instance.destroy()
            except Exception as destroy_error:
                raise ExceptionGroup(
                    "Computer instance could not be audited or destroyed",
                    [audit_error, destroy_error],
                )
            finally:
                async with self._lock:
                    self._instances.pop(instance.instance_id, None)
                    self._identities.pop(instance.instance_id, None)
            raise
        return instance

    async def _destroy_instance(self, instance: ComputerInstance) -> None:
        failures: list[Exception] = []
        destroyed = False
        try:
            if instance.instance_id not in self._created_audited:
                try:
                    self._record_lifecycle("computer.vm.created", instance)
                    self._created_audited.add(instance.instance_id)
                except Exception as exc:
                    failures.append(exc)
            try:
                await instance.destroy()
                destroyed = True
            except Exception as exc:
                failures.append(exc)
            if destroyed:
                try:
                    self._record_lifecycle("computer.vm.destroyed", instance)
                except Exception as exc:
                    failures.append(exc)
        finally:
            async with self._lock:
                self._instances.pop(instance.instance_id, None)
                self._identities.pop(instance.instance_id, None)
                self._created_audited.discard(instance.instance_id)
        if failures:
            raise ExceptionGroup("Computer instance cleanup was incomplete", failures)

    def _record_lifecycle(self, event: str, instance: ComputerInstance) -> None:
        if self.audit_log is None:
            return
        tenant_id, user_id, run_id = self._identities.get(instance.instance_id, _SYSTEM_IDENTITY)
        self.audit_log.record(
            event,
            run_id,
            tenant_id,
            user_id,
            instanceId=instance.instance_id,
        )

    @staticmethod
    def _identity(
        tenant_id: str | None,
        user_id: str | None,
        run_id: str | None,
    ) -> tuple[str, str, str]:
        if all(isinstance(value, str) and value for value in (tenant_id, user_id, run_id)):
            return tenant_id, user_id, run_id
        return _SYSTEM_IDENTITY

    async def _publish(self, instance: ComputerInstance) -> None:
        await self._available.put(instance)

    def _schedule_replenish(self) -> None:
        if self._replenish_task is None or self._replenish_task.done():
            self._replenish_task = asyncio.create_task(self._replenish())

    async def _replenish(self) -> None:
        try:
            while not self._closed:
                async with self._lock:
                    should_boot = (
                        self._available.qsize() + self._booting < self.config.warm_pool_size
                        and len(self._instances) + self._booting < self._instance_limit
                    )
                if not should_boot:
                    return
                async with self._lock:
                    if self._closed:
                        return
                    if (
                        self._available.qsize() + self._booting >= self.config.warm_pool_size
                        or len(self._instances) + self._booting >= self._instance_limit
                    ):
                        return
                    self._booting += 1
                instance = await self._boot_reserved(reserved=True)
                if self._closed:
                    await self._destroy_instance(instance)
                    return
                await self._publish(instance)
        except (ComputerUnavailableError, ComputerError):
            if not self._closed:
                logger.exception("Could not replenish the Firecracker computer pool")
