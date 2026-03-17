"""Tests for CLI check command."""

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
    resp._request = httpx.Request("GET", "http://test")
    return resp


class TestCheck:
    def test_granted_prints_oui(self, mocker):
        mock_cls = mocker.patch("dockmaster.cli.check.httpx.Client")
        mock_client = mock_cls.return_value.__enter__.return_value
        mock_client.get.return_value = _mock_response(status_code=204)

        result = runner.invoke(app, ["check", "user@x.com", "myapi", "-p", "read"])

        assert result.exit_code == 0
        assert "Oui!" in result.output

    def test_denied_prints_non(self, mocker):
        mock_cls = mocker.patch("dockmaster.cli.check.httpx.Client")
        mock_client = mock_cls.return_value.__enter__.return_value
        mock_client.get.return_value = _mock_response(
            status_code=403,
            json_data={"detail": "denied"},
        )

        result = runner.invoke(app, ["check", "user@x.com", "myapi", "-p", "read"])

        assert result.exit_code == 1
        assert "Non!" in result.output

    def test_server_error(self, mocker):
        mock_cls = mocker.patch("dockmaster.cli.check.httpx.Client")
        mock_client = mock_cls.return_value.__enter__.return_value
        mock_client.get.return_value = _mock_response(status_code=500, text="Internal error")

        result = runner.invoke(app, ["check", "user@x.com", "myapi", "-p", "read"])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_permission_flag_is_required(self):
        result = runner.invoke(app, ["check", "user@x.com", "myapi"])
        assert result.exit_code != 0
