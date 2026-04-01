"""RBAC permission resolution engine with TTL cache."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from google.api_core.exceptions import NotFound

from dockmaster.rbac.storage import SecretsStorage

logger = structlog.get_logger(__name__)


class Authority:
    """Resolves permissions using SecretsStorage with in-memory TTL caching.

    Lifespan-scoped singleton — cache persists across requests within TTL.
    """

    def __init__(self, storage: SecretsStorage, cache_ttl: int = 300) -> None:
        self._storage = storage
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[Any, float]] = {}

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _is_cached(self, key: str) -> bool:
        if key not in self._cache:
            return False
        return time.time() < self._cache[key][1]

    def _cache_get(self, key: str) -> Any:
        return self._cache[key][0]

    def _cache_set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, time.time() + self._cache_ttl)

    def clear_cache(self) -> None:
        """Clear all cached data. Used by admin writes to force fresh loads."""
        self._cache = {}

    # ------------------------------------------------------------------
    # Permission resolution
    # ------------------------------------------------------------------

    async def has_permission(self, subject: str, target: str, permission: str) -> bool:
        """Check if subject has permission for target service.

        Returns True if granted, False if denied (including target/subject not found).
        """
        # 1. Load service grants for target
        grants_key = f"grants:{target}"
        if self._is_cached(grants_key):
            service_grants = self._cache_get(grants_key)
        else:
            try:
                loop = asyncio.get_running_loop()
                service_grants = await loop.run_in_executor(None, self._storage.get_service_grants, target)
            except NotFound:
                logger.debug("target_not_found", target=target)
                return False
            self._cache_set(grants_key, service_grants)

        # 2. Find subject's grant entry
        grant = None
        for g in service_grants.grants:
            if g.subject == subject:
                grant = g
                break

        if grant is None:
            return False

        # 3. Load each role and collect permissions
        permissions_set: set[str] = set()
        for role_name in grant.roles:
            role_key = f"role:{role_name}"
            if self._is_cached(role_key):
                role = self._cache_get(role_key)
            else:
                try:
                    loop = asyncio.get_running_loop()
                    role = await loop.run_in_executor(None, self._storage.get_role, role_name)
                except NotFound:
                    logger.warning("role_not_found", role_name=role_name)
                    continue
                self._cache_set(role_key, role)
            permissions_set.update(role.permissions)

        # 4. Exact string match
        return permission in permissions_set

    async def get_permissions(self, subject: str, target: str) -> set[str]:
        """Return all permissions the subject has for the target service.

        Returns an empty set if the target or subject is not found.
        """
        # 1. Load service grants for target
        grants_key = f"grants:{target}"
        if self._is_cached(grants_key):
            service_grants = self._cache_get(grants_key)
        else:
            try:
                loop = asyncio.get_running_loop()
                service_grants = await loop.run_in_executor(None, self._storage.get_service_grants, target)
            except NotFound:
                logger.debug("target_not_found", target=target)
                return set()
            self._cache_set(grants_key, service_grants)

        # 2. Find subject's grant entry
        grant = None
        for g in service_grants.grants:
            if g.subject == subject:
                grant = g
                break

        if grant is None:
            return set()

        # 3. Load each role and collect permissions
        permissions_set: set[str] = set()
        for role_name in grant.roles:
            role_key = f"role:{role_name}"
            if self._is_cached(role_key):
                role = self._cache_get(role_key)
            else:
                try:
                    loop = asyncio.get_running_loop()
                    role = await loop.run_in_executor(None, self._storage.get_role, role_name)
                except NotFound:
                    logger.warning("role_not_found", role_name=role_name)
                    continue
                self._cache_set(role_key, role)
            permissions_set.update(role.permissions)

        return permissions_set
