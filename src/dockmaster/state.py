"""App state bridge dependencies.

Thin Depends-compatible functions that read singletons from ``app.state``.
Routes use these via ``Annotated[X | None, Depends(get_...)]`` to make
state dependencies visible in the function signature.

These are **not** auth concerns — they live outside ``auth/dependencies.py``.
"""

from __future__ import annotations

from fastapi import Request

from dockmaster.rbac.authority import Authority
from dockmaster.rbac.storage import AdminSecretsStorage
from dockmaster.sessions.protocol import SessionStore


def get_admin_storage(request: Request) -> AdminSecretsStorage | None:
    """Bridge: admin Secret Manager client from app.state."""
    return getattr(request.app.state, "admin_storage", None)


def get_authority(request: Request) -> Authority | None:
    """Bridge: RBAC authority from app.state."""
    return getattr(request.app.state, "authority", None)


def get_session_store(request: Request) -> SessionStore | None:
    """Bridge: session store from app.state."""
    return getattr(request.app.state, "session_store", None)
