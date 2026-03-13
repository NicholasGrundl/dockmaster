"""Tests for CLI auth — token storage, loading, and expiry."""

import time
from unittest.mock import patch

import pytest

from dockmaster.cli.auth import _save_token, load_token, require_token


@pytest.fixture
def token_dir(tmp_path):
    """Patch get_token_path to use a temp directory."""
    token_path = tmp_path / "credentials.json"
    with patch("dockmaster.cli.auth.get_token_path", return_value=token_path):
        yield token_path


class TestSaveAndLoadToken:
    def test_save_and_load(self, token_dir):
        _save_token("my-jwt", time.time() + 900)
        assert load_token() == "my-jwt"

    def test_load_returns_none_when_no_file(self, token_dir):
        assert load_token() is None

    def test_load_returns_none_when_expired(self, token_dir):
        _save_token("my-jwt", time.time() - 10)
        assert load_token() is None

    def test_load_returns_none_within_expiry_buffer(self, token_dir):
        """Token expiring within 30 seconds is treated as expired."""
        _save_token("my-jwt", time.time() + 15)
        assert load_token() is None

    def test_load_returns_token_outside_buffer(self, token_dir):
        """Token with >30 seconds remaining is valid."""
        _save_token("my-jwt", time.time() + 60)
        assert load_token() == "my-jwt"

    def test_load_returns_none_on_corrupt_file(self, token_dir):
        token_dir.write_text("not json")
        assert load_token() is None

    def test_save_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "credentials.json"
        with patch("dockmaster.cli.auth.get_token_path", return_value=nested):
            _save_token("my-jwt", time.time() + 900)
        assert nested.exists()


class TestRequireToken:
    def test_returns_valid_token(self, token_dir):
        _save_token("my-jwt", time.time() + 900)
        assert require_token() == "my-jwt"

    def test_exits_when_no_token(self, token_dir):
        import click

        with pytest.raises(click.exceptions.Exit):
            require_token()

    def test_exits_when_expired(self, token_dir):
        _save_token("my-jwt", time.time() - 10)
        import click

        with pytest.raises(click.exceptions.Exit):
            require_token()


class TestDeleteToken:
    def test_logout_deletes_file(self, token_dir):
        _save_token("my-jwt", time.time() + 900)
        assert token_dir.exists()

        from dockmaster.cli.auth import _delete_token

        _delete_token()
        assert not token_dir.exists()

    def test_logout_no_file_is_noop(self, token_dir):
        from dockmaster.cli.auth import _delete_token

        _delete_token()  # should not raise
