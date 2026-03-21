"""Unified OAuth flow store for login lifecycle.

Replaces the separate oauth_state_store (TTLStore[dict]) and auth_code_store
(AuthCodeStore) with a single store that manages both OAuth CSRF state and
login tickets through one consume() interface.

Callers use isinstance() to distinguish entry types:
    entry = flow_store.consume(key)
    if isinstance(entry, OAuthState):
        ...  # callback handling
    elif isinstance(entry, LoginTicket):
        ...  # code exchange
"""

from pydantic import BaseModel

from dockmaster.auth.ttl_store import TTLStore


class OAuthState(BaseModel):
    """CSRF state for an in-progress OAuth round-trip."""

    redirect_uri: str | None = None  # None = cookie flow, present = external/CLI
    return_to: str | None = None  # post-auth redirect target


class LoginTicket(BaseModel):
    """Pending login for an external app to claim via code exchange."""

    subject: str  # authenticated email
    redirect_uri: str  # must match on consume
    profile: dict = {}  # OAuth profile claims
    return_to: str | None = None  # forwarded from OAuthState


class OAuthFlowStore:
    """Unified single-use store for the OAuth login lifecycle.

    Two internal TTLStores (one for OAuth state, one for login tickets),
    one consume() method. Keys are cryptographically random tokens.
    Entries are single-use — consumed on retrieval.
    """

    def __init__(self, oauth_state_ttl: int = 600, login_ticket_ttl: int = 300) -> None:
        self._oauth_states = TTLStore[OAuthState](ttl=oauth_state_ttl)
        self._login_tickets = TTLStore[LoginTicket](ttl=login_ticket_ttl)

    def create_oauth_state(
        self,
        redirect_uri: str | None = None,
        return_to: str | None = None,
    ) -> str:
        """Store an OAuth CSRF state entry. Returns the state key."""
        entry = OAuthState(redirect_uri=redirect_uri, return_to=return_to)
        return self._oauth_states.create(entry)

    def create_login_ticket(
        self,
        subject: str,
        redirect_uri: str,
        profile: dict | None = None,
        return_to: str | None = None,
    ) -> str:
        """Store a login ticket for code exchange. Returns the ticket code."""
        entry = LoginTicket(
            subject=subject,
            redirect_uri=redirect_uri,
            profile=profile or {},
            return_to=return_to,
        )
        return self._login_tickets.create(entry)

    def consume(self, key: str) -> OAuthState | LoginTicket | None:
        """Consume an entry by key. Returns the entry or None.

        Tries OAuth states first, then login tickets. The entry is deleted
        on retrieval (single-use). Returns None if the key doesn't exist
        or has expired.
        """
        entry = self._oauth_states.consume(key)
        if entry is not None:
            return entry
        return self._login_tickets.consume(key)
