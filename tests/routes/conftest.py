"""Route endpoint test fixtures.

Fixtures defined here:
  - auth_client: TestClient with app.state.realm wired to the fake realm

Inherited from tests/conftest.py:
  - fixtures_dir, test_settings, app, client, test_app_factory
  - fake_sa_key_data, fake_realm, signer, valid_token
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockmaster.auth.jwt_verifier import ServiceRealm


@pytest.fixture
def auth_client(app: FastAPI, fake_realm: ServiceRealm) -> TestClient:
    """TestClient with app.state.realm wired to the fake realm."""
    with TestClient(app) as client:
        app.state.realm = fake_realm
        yield client
