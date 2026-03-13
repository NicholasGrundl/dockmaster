"""Tests for CLI role commands — all API calls mocked via httpx."""

from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from dockmaster.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def mock_auth():
    """Bypass token check for all CLI command tests."""
    with patch("dockmaster.cli.auth.load_token", return_value="fake-jwt"):
        yield


def _mock_response(status_code=200, json_data=None, text=None):
    kwargs = {"status_code": status_code}
    if json_data is not None:
        kwargs["json"] = json_data
    elif text is not None:
        kwargs["text"] = text
    resp = httpx.Response(**kwargs)
    resp._request = httpx.Request("GET", "http://test")
    return resp


class TestRoleList:
    def test_lists_roles(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.return_value = _mock_response(json_data=["admin", "viewer"])

            result = runner.invoke(app, ["role", "list"])

        assert result.exit_code == 0
        assert '"admin"' in result.output
        assert '"viewer"' in result.output


class TestRoleGet:
    def test_gets_role(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.return_value = _mock_response(
                json_data={"name": "admin", "permissions": ["read", "write"]}
            )

            result = runner.invoke(app, ["role", "get", "admin"])

        assert result.exit_code == 0
        assert '"admin"' in result.output
        assert '"read"' in result.output

    def test_get_not_found(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.return_value = _mock_response(
                status_code=404, json_data={"detail": "Role 'nope' not found"}
            )

            result = runner.invoke(app, ["role", "get", "nope"])

        assert result.exit_code == 1


class TestRoleCreate:
    def test_creates_role(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.return_value = _mock_response(
                status_code=201, json_data={"name": "editor", "permissions": ["read", "write"]}
            )

            result = runner.invoke(app, ["role", "create", "editor", "-p", "read", "-p", "write"])

        assert result.exit_code == 0
        assert '"editor"' in result.output

    def test_create_requires_permission(self):
        result = runner.invoke(app, ["role", "create", "empty"])
        assert result.exit_code == 1
        assert "--permission" in result.output


class TestRoleDelete:
    def test_deletes_role(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.return_value = _mock_response(status_code=204)

            result = runner.invoke(app, ["role", "delete", "old-role"])

        assert result.exit_code == 0
        assert "deleted" in result.output


class TestRoleAdd:
    def test_adds_permission(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            # First call: GET current role, second call: PUT updated role
            mock_client.request.side_effect = [
                _mock_response(json_data={"name": "admin", "permissions": ["read"]}),
                _mock_response(json_data={"name": "admin", "permissions": ["read", "write"]}),
            ]

            result = runner.invoke(app, ["role", "add", "admin", "-p", "write"])

        assert result.exit_code == 0
        # Verify the PUT was called with merged permissions
        put_call = mock_client.request.call_args_list[1]
        body = put_call.kwargs.get("json") or put_call[1].get("json")
        assert set(body["permissions"]) == {"read", "write"}

    def test_add_requires_permission(self):
        result = runner.invoke(app, ["role", "add", "admin"])
        assert result.exit_code == 1


class TestRoleRemove:
    def test_removes_permission(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.side_effect = [
                _mock_response(json_data={"name": "admin", "permissions": ["read", "write", "delete"]}),
                _mock_response(json_data={"name": "admin", "permissions": ["read", "write"]}),
            ]

            result = runner.invoke(app, ["role", "remove", "admin", "-p", "delete"])

        assert result.exit_code == 0
        put_call = mock_client.request.call_args_list[1]
        body = put_call.kwargs.get("json") or put_call[1].get("json")
        assert "delete" not in body["permissions"]

    def test_remove_requires_permission(self):
        result = runner.invoke(app, ["role", "remove", "admin"])
        assert result.exit_code == 1
