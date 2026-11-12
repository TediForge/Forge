"""Cache for lazily created model backends."""

import threading
from typing import Generic, TypeVar


T = TypeVar("T")


class RuntimeCache(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], T] = {}
        self._lock = threading.Lock()

    def get(self, model_id: str, backend_id: str) -> T | None:
        with self._lock:
            return self._items.get((model_id, backend_id))

    def set(self, model_id: str, backend_id: str, value: T) -> None:
        with self._lock:
            self._items[(model_id, backend_id)] = value

    def values(self) -> list[T]:
        with self._lock:
            return list(self._items.values())

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
