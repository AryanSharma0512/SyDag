"""
Disk cache for external context data.

Government services are slow and sometimes down, and a demo must not depend on
them answering. Each entry is a JSON file stamped with its retrieval time. An
entry past its TTL is refreshed, but if the refresh fails the old entry is
served instead (marked stale), so a field that loaded once keeps loading.
"""

import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.context.http import UpstreamError


@dataclass(frozen=True)
class Cached:
    value: Any
    retrieved_at: datetime
    stale: bool  # served because a refresh failed


class ContextCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._locks: dict[Path, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.root / namespace / f"{digest}.json"

    def _lock(self, path: Path) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(path, threading.Lock())

    @staticmethod
    def _read(path: Path) -> Cached | None:
        try:
            raw = json.loads(path.read_text())
            return Cached(raw["value"], datetime.fromisoformat(raw["retrievedAt"]), stale=False)
        except (OSError, ValueError, KeyError):
            return None

    @staticmethod
    def _write(path: Path, value: Any, retrieved_at: datetime) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump({"retrievedAt": retrieved_at.isoformat(), "value": value}, f)
        os.replace(tmp, path)

    def get_or_fetch(
        self, namespace: str, key: str, ttl: timedelta | None, fetch: Callable[[], Any]
    ) -> Cached:
        """Cached value if fresh, else fetch(). `ttl=None` never expires.
        One fetch per key at a time, so concurrent requests don't stampede a service."""
        path = self._path(namespace, key)
        with self._lock(path):
            cached = self._read(path)
            now = datetime.now(UTC)
            if cached and (ttl is None or now - cached.retrieved_at < ttl):
                return cached
            try:
                value = fetch()
            except UpstreamError:
                if cached:
                    return Cached(cached.value, cached.retrieved_at, stale=True)
                raise
            try:
                self._write(path, value, now)
            except OSError:
                pass  # an unwritable cache must not break live responses
            return Cached(value, now, stale=False)


@lru_cache
def get_context_cache() -> ContextCache:
    return ContextCache(get_settings().cache_dir)
