import pytest
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from dockmaster.session.schemas import SessionData, SessionID, SessionInterface
from dockmaster.session.memory_session import MemorySession

@pytest.fixture
def session_data_dict()->dict:
    return {
        'kind' : 'dict',
        'user' : 'test_user',
        'state' : '12345',
        'nonce' : '678910',
        'created_at' : datetime.now(timezone.utc),
    }

@pytest.fixture
def session_data_pydantic()->BaseModel:
    class Data(BaseModel):
        kind : str = 'pydantic'
        user: str = 'test_user'
        state: str = '12345'
        nonce: str = '678910'
        created_at: datetime = datetime.now(timezone.utc)
    return Data()

@pytest.fixture
def memory_session() -> SessionInterface:
    """Fixture for creating a clean MemoryCache instance"""
    return MemorySession()  # Each test gets a fresh instance


def test_store_dict_data(memory_session: SessionInterface, session_data_dict: dict):
    """Test storing a dictionary"""
    session_data = session_data_dict
    session_id = memory_session.store_session(session = session_data_dict)
    assert isinstance(session_id, str)
    
    retrieved_session = memory_session.retrieve_session(session_id)
    assert retrieved_session == session_data
    
    removed_session = memory_session.remove_session(session_id)
    assert removed_session == session_data
    assert memory_session.retrieve_session(session_id) is None

def test_store_pydantic_data(memory_session: SessionInterface, session_data_pydantic: BaseModel):
    """Test storing an AuthenticationFlowSession"""
    session_data = session_data_pydantic
    session_id = memory_session.store_session(session = session_data)
    assert isinstance(session_id, str)
    
    retrieved_session = memory_session.retrieve_session(session_id)
    assert retrieved_session == session_data
    
    removed_session = memory_session.remove_session(session_id)
    assert removed_session == session_data
    assert memory_session.retrieve_session(session_id) is None

def test_nonexistent_session(memory_session: SessionInterface):
    """Test retrieving a non-existent session"""
    assert memory_session.retrieve_session("nonexistent") is None
    assert memory_session.remove_session("nonexistent") is None

