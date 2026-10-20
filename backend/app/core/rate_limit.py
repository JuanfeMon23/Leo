"""Limitador de ventana deslizante en memoria del proceso.

Lo usa el login (por IP y por usuario). Pendiente: con varias instancias
del backend debe vivir en un almacen compartido (Redis); en memoria cada
proceso cuenta por separado.
"""

import threading
from collections import deque
from datetime import datetime

from app.core import clock


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()
        return hits

    def retry_after(self, key: str, at: datetime | None = None) -> int:
        """Segundos hasta poder volver a intentar; 0 si no esta limitado."""
        now = (at or clock.now()).timestamp()
        with self._lock:
            hits = self._recent(key, now)
            if len(hits) < self.limit:
                return 0
            return int(hits[0] + self.window_seconds - now) + 1

    def hit(self, key: str, at: datetime | None = None) -> None:
        now = (at or clock.now()).timestamp()
        with self._lock:
            self._recent(key, now).append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
