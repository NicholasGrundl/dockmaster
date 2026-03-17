"""CLI test fixtures.

Fixtures defined here:
  - mock_cli_auth: auto-use fixture that bypasses token check for all CLI tests

Inherited from tests/conftest.py:
  - fixtures_dir, test_settings, app, client
"""

import pytest


@pytest.fixture(autouse=True)
def mock_cli_auth(mocker):
    """Bypass token check for all CLI command tests."""
    return mocker.patch("dockmaster.cli.auth.load_token", return_value="fake-jwt")
