"""Pydantic modesl and interfaces for session management."""
from abc import ABC, abstractmethod
from typing import  Any

from pydantic import BaseModel

SessionData = dict[str,Any] | BaseModel
SessionID = str

# Interfaces
class SessionInterface(ABC):
    """Interface to various session storage backends"""
    @abstractmethod
    def store_data(self, session: SessionData) -> SessionID:
        """Store a session in the cache, overwrite if present"""
        pass
        
    @abstractmethod
    def retrieve_data(self, session_id: SessionID) -> SessionData | None:
        """Retrieve a session from the cache if present as a view
        
        - validate session expiry
        """
        pass
        
    @abstractmethod
    def remove_data(self, session_id: SessionID) -> SessionData | None:
        """Remove a session from the cache return it if present """
        pass
        