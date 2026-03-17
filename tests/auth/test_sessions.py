"""Tests for InMemorySessionStore — TDD (Red → Green)."""

import time

import pytest

from dockmaster.sessions.memory import InMemorySessionStore


@pytest.fixture
def store() -> InMemorySessionStore:
    return InMemorySessionStore()


class TestInMemorySessionStore:
    """Core CRUD operations."""

    async def test_set_and_get(self, store):
        await store.set("sid-1", {"email": "user@example.com"})
        result = await store.get("sid-1")
        assert result == {"email": "user@example.com"}

    async def test_get_nonexistent_returns_none(self, store):
        result = await store.get("does-not-exist")
        assert result is None

    async def test_delete_removes_session(self, store):
        await store.set("sid-1", {"email": "user@example.com"})
        await store.delete("sid-1")
        result = await store.get("sid-1")
        assert result is None

    async def test_delete_nonexistent_is_idempotent(self, store):
        await store.delete("does-not-exist")  # should not raise

    async def test_set_overwrites_existing(self, store):
        await store.set("sid-1", {"email": "old@example.com"})
        await store.set("sid-1", {"email": "new@example.com"})
        result = await store.get("sid-1")
        assert result == {"email": "new@example.com"}


class TestInMemorySessionStoreTTL:
    """TTL expiry behavior."""

    async def test_expired_session_returns_none(self, store, monkeypatch):
        await store.set("sid-1", {"email": "user@example.com"}, ttl=10)

        # Fast-forward time past TTL
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + 11)

        result = await store.get("sid-1")
        assert result is None

    async def test_not_expired_session_returns_data(self, store, monkeypatch):
        await store.set("sid-1", {"email": "user@example.com"}, ttl=60)

        # Still within TTL
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + 30)

        result = await store.get("sid-1")
        assert result == {"email": "user@example.com"}

    async def test_expired_session_is_cleaned_up(self, store, monkeypatch):
        """Expired entries are removed from internal storage on get()."""
        await store.set("sid-1", {"email": "user@example.com"}, ttl=10)

        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + 11)

        await store.get("sid-1")
        # Internal storage should no longer contain the entry
        assert "sid-1" not in store._store

    async def test_default_ttl(self, store):
        """Default TTL is 3600 seconds."""
        await store.set("sid-1", {"email": "user@example.com"})
        _data, expiry = store._store["sid-1"]
        assert expiry == pytest.approx(time.time() + 3600, abs=2)


class TestInMemorySessionStoreListAll:
    """list_all() behavior."""

    async def test_list_all_empty(self, store):
        result = await store.list_all()
        assert result == {}

    async def test_list_all_returns_active_sessions(self, store):
        await store.set("sid-1", {"email": "a@example.com"})
        await store.set("sid-2", {"email": "b@example.com"})
        result = await store.list_all()
        assert len(result) == 2
        assert result["sid-1"]["email"] == "a@example.com"
        assert result["sid-2"]["email"] == "b@example.com"
        # Each entry includes _expiry metadata
        assert "_expiry" in result["sid-1"]
        assert "_expiry" in result["sid-2"]

    async def test_list_all_excludes_expired(self, store, monkeypatch):
        await store.set("sid-1", {"email": "a@example.com"}, ttl=10)
        await store.set("sid-2", {"email": "b@example.com"}, ttl=600)

        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + 11)

        result = await store.list_all()
        assert "sid-1" not in result
        assert "sid-2" in result

    async def test_list_all_cleans_up_expired(self, store, monkeypatch):
        """Expired entries are removed from internal storage."""
        await store.set("sid-1", {"email": "a@example.com"}, ttl=10)

        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + 11)

        await store.list_all()
        assert "sid-1" not in store._store
