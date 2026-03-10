"""Shared pytest fixtures for dockmaster tests."""

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockmaster.config import Settings, get_settings
from dockmaster.main import create_app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# RSA key pair fixtures (session-scoped — generated once per test run)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_private_key():
    """Generate a 2048-bit RSA private key for testing."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def rsa_private_key_pem(rsa_private_key) -> str:
    """PEM-encoded private key string."""
    return rsa_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@pytest.fixture(scope="session")
def rsa_public_key_pem(rsa_private_key) -> str:
    """PEM-encoded public key string (SubjectPublicKeyInfo / SPKI format)."""
    return (
        rsa_private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


@pytest.fixture(scope="session")
def fake_sa_key_data(rsa_private_key_pem) -> dict:
    """A fake GCP service account key JSON structure with the test private key."""
    return {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id-001",
        "private_key": rsa_private_key_pem,
        "client_email": "test-sa@test-project.iam.gserviceaccount.com",
        "client_id": "000000000000000000000",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test-sa%40test-project.iam.gserviceaccount.com",
    }


@pytest.fixture(scope="session")
def fake_sa_key_path(tmp_path_factory, fake_sa_key_data) -> Path:
    """Write fake SA key to a temp file and return its path."""
    path = tmp_path_factory.mktemp("keys") / "fake_sa_key.json"
    path.write_text(json.dumps(fake_sa_key_data))
    return path


# ---------------------------------------------------------------------------
# GCP fixture loading helpers
# ---------------------------------------------------------------------------

GCP_FIXTURES_DIR = FIXTURES_DIR / "gcp"


@pytest.fixture
def iam_list_service_accounts():
    """Load captured IAM list service accounts fixture."""
    path = GCP_FIXTURES_DIR / "iam" / "list_service_accounts.json"
    if path.exists():
        return json.loads(path.read_text())
    pytest.skip("Fixture not captured yet: iam/list_service_accounts.json")


@pytest.fixture
def google_oidc_certs():
    """Load captured Google OIDC certs fixture."""
    path = GCP_FIXTURES_DIR / "google_oidc" / "v1_certs.json"
    if path.exists():
        return json.loads(path.read_text())
    pytest.skip("Fixture not captured yet: google_oidc/v1_certs.json")


@pytest.fixture
def test_settings() -> Settings:
    """Settings with safe test defaults - no real GCP credentials."""
    return Settings(
        log_level="DEBUG",
        authorized_issuers={"https://accounts.google.com"},
        authorized_domains={"example.com"},
        authorized_audience={"test-audience"},
        client_id="test-client-id",
        client_secret="test-client-secret",
        session_secret_key="test-secret-key",
    )


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    """FastAPI app wired with test settings."""
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: test_settings
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Synchronous test client for the app."""
    with TestClient(app) as c:
        yield c
