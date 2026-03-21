"""App state bridge dependencies (``get_*`` prefix).

Thin Depends-compatible functions that read singletons from ``app.state``.
Routes use these via ``Annotated[X | None, Depends(get_...)]`` to make
state dependencies visible in the function signature.

These follow the ``get_*`` prefix convention from the dependency taxonomy::

    get_*  →  Info / data  →  Returns value or None, never raises  →  Route-level

The ``get_*`` prefix signals that these are **soft** dependencies: they return
data (or a default) and never raise. They are distinct from ``needs_*``
dependencies (which raise 503 on missing infrastructure) and ``allow_*``
dependencies (which enforce authentication).

These are **not** auth concerns — they live outside ``auth/dependencies.py``.
Auth-related ``get_*`` dependencies (``get_jwt_claims``, ``get_session_user``,
``get_google_claims``) live in ``auth/dependencies.py`` because they interact
with credentials.
"""

from authlib.integrations.starlette_client import OAuth
from fastapi import Request

from dockmaster.auth.jwt_signers import EphemeralKeypairSigner
from dockmaster.auth.jwt_verifier import ServiceRealm
from dockmaster.auth.oauth_flow_store import OAuthFlowStore
from dockmaster.rbac.authority import Authority
from dockmaster.rbac.storage import AdminSecretsStorage
from dockmaster.sessions.protocol import SessionStore
from dockmaster.ui.config import UIConfig


def get_admin_storage(request: Request) -> AdminSecretsStorage | None:
    """Bridge: admin Secret Manager client from app.state."""
    return getattr(request.app.state, "admin_storage", None)


def get_authority(request: Request) -> Authority | None:
    """Bridge: RBAC authority from app.state."""
    return getattr(request.app.state, "authority", None)


def get_session_store(request: Request) -> SessionStore | None:
    """Bridge: session store from app.state."""
    return getattr(request.app.state, "session_store", None)


def get_ui_config(request: Request) -> UIConfig:
    """Bridge: UI branding/config from app.state (defaults to UIConfig())."""
    return getattr(request.app.state, "ui_config", UIConfig())


def get_token_issuer(request: Request) -> EphemeralKeypairSigner | None:
    """Bridge: ephemeral keypair signer for Type C JWT issuance from app.state."""
    return getattr(request.app.state, "token_issuer", None)


def get_flow_store(request: Request) -> OAuthFlowStore | None:
    """Bridge: OAuth flow store (CSRF state + login tickets) from app.state."""
    return getattr(request.app.state, "flow_store", None)


def get_oauth(request: Request) -> OAuth | None:
    """Bridge: Authlib OAuth client from app.state."""
    return getattr(request.app.state, "oauth", None)


def get_realm(request: Request) -> ServiceRealm | None:
    """Bridge: JWT verification realm (key caches) from app.state."""
    return getattr(request.app.state, "realm", None)
