"""Create specific sessions with rules"""
import uuid
from datetime import datetime, timedelta, timezone

from .schemas import SessionID, SessionData
from .schemas import SessionInterface
from .memory_session import MemorySession


def create_session_id()->SessionID:
    return str(uuid.uuid4())

class AuthenticationSessionManager:
    """Manages server-side session storage in memory for authentication SSO flow
    """

    def __init__(self, expiration_minutes: int = 5):
        self.session: SessionInterface = MemorySession(create_session_id=create_session_id)
        self.expiration_minutes = expiration_minutes
    
    def create_expiration_datetime(self)->datetime:
        return datetime.now(timezone.utc) + timedelta(minutes=self.expiration_minutes)
    
    def create_creation_datetime(self)->datetime:
        return datetime.now(timezone.utc)
    