"""Redis-backed rate limiting with an in-process fallback."""

from __future__ import annotations

import logging
import threading
import time

from app.core.config import settings
from app.core.errors import RateLimitError

logger = logging.getLogger(__name__)

try:  # pragma: no cover - import guard
    import redis
except Exception:  # pragma: no cover
    redis = None


class _MemoryBackend:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, float]] = {}

    def incr(self, key: str, window_seconds: int) -> int:
        now = time.time()
        with self._lock:
            count, expires_at = self._buckets.get(key, (0, now + window_seconds))
            if now >= expires_at:
                count, expires_at = 0, now + window_seconds
            count += 1
            self._buckets[key] = (count, expires_at)
            if len(self._buckets) > 10_000:
                for stale in [k for k, (_, exp) in self._buckets.items() if exp < now]:
                    self._buckets.pop(stale, None)
            return count


class RateLimiter:
    def __init__(self) -> None:
        self._memory = _MemoryBackend()
        self._redis = None
        if redis is not None:
            try:
                self._redis = redis.Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                )
                self._redis.ping()
            except Exception:  # pragma: no cover - redis optional
                logger.warning("Redis unavailable for rate limiting; using in-memory backend.")
                self._redis = None

    def hit(self, scope: str, identity: str, limit: int, window_seconds: int = 60) -> None:
        if not settings.rate_limit_enabled or limit <= 0:
            return
        key = f"nexus:rl:{scope}:{identity}:{int(time.time() // window_seconds)}"
        try:
            if self._redis is not None:
                count = self._redis.incr(key)
                if count == 1:
                    self._redis.expire(key, window_seconds + 1)
            else:
                count = self._memory.incr(key, window_seconds)
        except Exception:  # pragma: no cover - redis hiccup must not break requests
            count = self._memory.incr(key, window_seconds)
        if count > limit:
            raise RateLimitError("Too many requests. Please try again later.")


limiter = RateLimiter()
