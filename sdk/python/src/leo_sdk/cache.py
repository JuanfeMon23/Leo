"""Cache en memoria con TTL (introspeccion, resultados de refresh)."""

import time
from collections.abc import Callable


class TTLCache[V]:
    """Cache acotada con expiracion por entrada. `ttl_seconds <= 0` la
    desactiva (nunca guarda). No es segura entre procesos."""

    def __init__(
        self,
        ttl_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = 10_000,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._max = max_entries
        self._items: dict[str, tuple[float, V]] = {}

    def __len__(self) -> int:
        return len(self._items)

    def get(self, key: str) -> V | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires, value = item
        if expires <= self._clock():
            del self._items[key]
            return None
        return value

    def set(self, key: str, value: V) -> None:
        if self._ttl <= 0:
            return
        now = self._clock()
        if len(self._items) >= self._max and key not in self._items:
            self._items = {k: v for k, v in self._items.items() if v[0] > now}
            while len(self._items) >= self._max:  # sigue lleno: descarta el mas viejo
                del self._items[next(iter(self._items))]
        self._items[key] = (now + self._ttl, value)

    def delete(self, key: str) -> None:
        self._items.pop(key, None)

    def clear(self) -> None:
        self._items.clear()
