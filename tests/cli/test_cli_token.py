"""Tests for CLI token command."""

import httpx
from typer.testing import CliRunner

from dockmaster.cli.main import app

runner = CliRunner()


def _mock_response(status_code=200, json_data=None, text=None):
    kwargs = {"status_code": status_code}
    if json_data is not None:
        kwargs["json"] = json_data
    elif text is not None:
        kwargs["text"] = text
    resp = httpx.Response(**kwargs)
    resp._request = httpx.Request("POST", "http://test")
    return resp


class TestTokenCommand:
    def test_prints_token_to_stdout(self, mocker):
        """dockmaster token billing → prints access_token."""
        mock_cls = mocker.patch("dockmaster.cli.token.httpx.Client")
        mock_client = mock_cls.return_value.__enter__.return_value
        mock_client.post.return_value = _mock_response(
            json_data={
                "access_token": "eyJ.test.token",
                "token_type": "bearer",
                "expires_in": 900,
                "refresh_token": None,
            }
        )

        result = runner.invoke(app, ["token", "billing"])

        assert result.exit_code == 0
        assert result.output.strip() == "eyJ.test.token"

    def test_passes_service_param(self, mocker):
        """Service argument is sent as query param."""
        mock_cls = mocker.patch("dockmaster.cli.token.httpx.Client")
        mock_client = mock_cls.return_value.__enter__.return_value
        mock_client.post.return_value = _mock_response(
            json_data={"access_token": "tok", "token_type": "bearer", "expires_in": 900, "refresh_token": None}
        )

        runner.invoke(app, ["token", "analytics"])

        mock_client.post.assert_called_once_with(
            "/auth/token",
            params={"service": "analytics"},
            headers={"Authorization": "Bearer fake-jwt"},
        )

    def test_server_error_exits_1(self, mocker):
        """Server error → exit code 1 with error message."""
        mock_cls = mocker.patch("dockmaster.cli.token.httpx.Client")
        mock_client = mock_cls.return_value.__enter__.return_value
        mock_client.post.return_value = _mock_response(status_code=401, json_data={"detail": "Not authenticated"})

        result = runner.invoke(app, ["token", "billing"])

        assert result.exit_code == 1
        assert "Not authenticated" in result.output

    def test_not_logged_in_exits_1(self, mocker):
        """No stored token → exit code 1 with login prompt."""
        mocker.patch("dockmaster.cli.auth.load_token", return_value=None)
        result = runner.invoke(app, ["token", "billing"])

        assert result.exit_code == 1
        assert "login" in result.output.lower()

    def test_service_argument_required(self):
        """No service argument → usage error."""
        result = runner.invoke(app, ["token"])
        assert result.exit_code != 0
