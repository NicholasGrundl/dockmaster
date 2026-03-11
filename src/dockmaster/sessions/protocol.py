"""Session store protocol — interface for session backends."""

from __future__ import annotations

from typing import Protocol


class SessionStore(Protocol):
    """Minimal session store interface.

    Implementations: InMemorySessionStore (dev), Redis (prod).
    """

    async def get(self, session_id: str) -> dict | None: ...
    async def set(self, session_id: str, data: dict, ttl: int = 3600) -> None: ...
    async def delete(self, session_id: str) -> None: ...
