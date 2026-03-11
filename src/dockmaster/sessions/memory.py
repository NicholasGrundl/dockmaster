"""In-memory session store — suitable for development and single-process deployments."""

from __future__ import annotations

import time


class InMemorySessionStore:
    """Dict-backed session store with lazy TTL expiry."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[dict, float]] = {}

    async def get(self, session_id: str) -> dict | None:
        entry = self._store.get(session_id)
        if entry is None:
            return None

        data, expiry = entry
        if time.time() > expiry:
            del self._store[session_id]
            return None

        return data

    async def set(self, session_id: str, data: dict, ttl: int = 3600) -> None:
        self._store[session_id] = (data, time.time() + ttl)

    async def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)
