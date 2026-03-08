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
    session_id = memory_session.store_data(session = session_data_dict)
    assert isinstance(session_id, str)
    
    retrieved_session = memory_session.retrieve_data(session_id)
    assert retrieved_session == session_data
    
    removed_session = memory_session.remove_data(session_id)
    assert removed_session == session_data
    assert memory_session.retrieve_data(session_id) is None

def test_store_pydantic_data(memory_session: SessionInterface, session_data_pydantic: BaseModel):
    """Test storing an AuthenticationFlowSession"""
    session_data = session_data_pydantic
    session_id = memory_session.store_data(session = session_data)
    assert isinstance(session_id, str)
    
    retrieved_session = memory_session.retrieve_data(session_id)
    assert retrieved_session == session_data
    
    removed_session = memory_session.remove_data(session_id)
    assert removed_session == session_data
    assert memory_session.retrieve_data(session_id) is None

def test_nonexistent_session(memory_session: SessionInterface):
    """Test retrieving a non-existent session"""
    assert memory_session.retrieve_data("nonexistent") is None
    assert memory_session.remove_data("nonexistent") is None


# def test_dictionary_like_behavior(memory_session: SessionInterface, session_data_dict: dict):
#     """Test dictionary like behavior"""
#     session_data = session_data_dict
#     session_id = memory_session.store_data(session = session_data)
#     # Get and Delete methods
#     assert memory_session[session_id] == session_data
#     assert memory_session.get(session_id) == session_data
#     assert memory_session.get("nonexistent") is None
#     assert session_id in memory_session
#     assert len(memory_session) == 1
#     del memory_session[session_id]
#     assert session_id not in memory_session
#     assert len(memory_session) == 0

#     # Set methods
#     memory_session[session_id] = session_data
#     assert memory_session[session_id] == session_data
#     del memory_session[session_id]
#     memory_session.set(session_id, session_data)
#     assert memory_session[session_id] == session_data
#     del memory_session[session_id]

#     # Pop methods
#     for i in range(5):
#         memory_session[f"session_{i}"] = session_data
#     assert len(memory_session) == 5
#     assert memory_session.pop("session_0") == session_data
#     assert len(memory_session) == 4
#     memory_session.clear()
#     assert len(memory_session) == 0