"""Simple In-Memory cache of python objects"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Callable
from datetime import datetime, timezone
from collections.abc import MutableMapping

from .schemas import SessionData, SessionID
from .schemas import SessionInterface

class MemorySession(SessionInterface):
    """Simple in-memory cache for session storage"""
    def __init__(self, session_id_fn: Callable[[],SessionID] | None = None):
        """Initialize an empty session storage with id creation
        
        session_id_fn: function to create a session id
        """
        self._sessions: Dict[str, SessionData] = {}
        
        self._create_session_id = session_id_fn or (lambda: str(uuid.uuid4()))
    
    def store_data(self, session: SessionData) -> SessionID:
        """Store a session in the cache"""
        session_id = self._create_session_id()
        self._sessions[session_id] = session
        return session_id
    
    def retrieve_data(self, session_id: SessionID) -> SessionData | None:
        """Retrieve a session from the cache"""
        session = self._sessions.get(session_id, None)
        return session
    
    def remove_data(self, session_id: SessionID) -> SessionData | None:
        """Remove a session from the cache return it if present """
        session = self._sessions.pop(session_id, None)
        return session