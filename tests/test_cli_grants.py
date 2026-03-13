"""Tests for CLI grant commands — all API calls mocked via httpx."""

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


class TestGrantList:
    def test_lists_services(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.return_value = _mock_response(json_data=["dockmaster", "myapi"])

            result = runner.invoke(app, ["grant", "list"])

        assert result.exit_code == 0
        assert '"dockmaster"' in result.output
        assert '"myapi"' in result.output


class TestGrantGet:
    def test_gets_grants(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.return_value = _mock_response(
                json_data={
                    "service": "myapi",
                    "grants": [{"subject": "user@x.com", "roles": ["viewer"]}],
                }
            )

            result = runner.invoke(app, ["grant", "get", "myapi"])

        assert result.exit_code == 0
        assert '"user@x.com"' in result.output


class TestGrantAdd:
    def test_adds_to_existing_service(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.side_effect = [
                # GET existing grants
                _mock_response(
                    json_data={
                        "service": "myapi",
                        "grants": [{"subject": "existing@x.com", "roles": ["admin"]}],
                    }
                ),
                # POST merged grants
                _mock_response(
                    json_data={
                        "service": "myapi",
                        "grants": [
                            {"subject": "existing@x.com", "roles": ["admin"]},
                            {"subject": "new@x.com", "roles": ["viewer"]},
                        ],
                    }
                ),
            ]

            result = runner.invoke(app, ["grant", "add", "myapi", "new@x.com", "-r", "viewer"])

        assert result.exit_code == 0
        # Verify POST included both subjects
        post_call = mock_client.request.call_args_list[1]
        body = post_call.kwargs.get("json") or post_call[1].get("json")
        subjects = [g["subject"] for g in body["grants"]]
        assert "existing@x.com" in subjects
        assert "new@x.com" in subjects

    def test_creates_new_service_on_404(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.side_effect = [
                # GET returns 404 (service doesn't exist)
                _mock_response(status_code=404, json_data={"detail": "not found"}),
                # POST creates fresh
                _mock_response(
                    json_data={
                        "service": "new-svc",
                        "grants": [{"subject": "user@x.com", "roles": ["viewer"]}],
                    }
                ),
            ]

            result = runner.invoke(app, ["grant", "add", "new-svc", "user@x.com", "-r", "viewer"])

        assert result.exit_code == 0
        assert '"new-svc"' in result.output

    def test_merges_roles_for_existing_subject(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.side_effect = [
                _mock_response(
                    json_data={
                        "service": "myapi",
                        "grants": [{"subject": "user@x.com", "roles": ["viewer"]}],
                    }
                ),
                _mock_response(
                    json_data={
                        "service": "myapi",
                        "grants": [{"subject": "user@x.com", "roles": ["viewer", "editor"]}],
                    }
                ),
            ]

            result = runner.invoke(app, ["grant", "add", "myapi", "user@x.com", "-r", "editor"])

        assert result.exit_code == 0
        post_call = mock_client.request.call_args_list[1]
        body = post_call.kwargs.get("json") or post_call[1].get("json")
        roles = body["grants"][0]["roles"]
        assert set(roles) == {"viewer", "editor"}

    def test_add_requires_role(self):
        result = runner.invoke(app, ["grant", "add", "myapi", "user@x.com"])
        assert result.exit_code == 1
        assert "--role" in result.output


class TestGrantRemove:
    def test_removes_specific_role(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.side_effect = [
                _mock_response(
                    json_data={
                        "service": "myapi",
                        "grants": [{"subject": "user@x.com", "roles": ["viewer", "editor"]}],
                    }
                ),
                _mock_response(
                    json_data={
                        "service": "myapi",
                        "grants": [{"subject": "user@x.com", "roles": ["viewer"]}],
                    }
                ),
            ]

            result = runner.invoke(app, ["grant", "remove", "myapi", "user@x.com", "-r", "editor"])

        assert result.exit_code == 0
        post_call = mock_client.request.call_args_list[1]
        body = post_call.kwargs.get("json") or post_call[1].get("json")
        assert body["grants"][0]["roles"] == ["viewer"]

    def test_removes_all_roles_without_flag(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.side_effect = [
                _mock_response(
                    json_data={
                        "service": "myapi",
                        "grants": [
                            {"subject": "user@x.com", "roles": ["viewer"]},
                            {"subject": "other@x.com", "roles": ["admin"]},
                        ],
                    }
                ),
                _mock_response(
                    json_data={
                        "service": "myapi",
                        "grants": [{"subject": "other@x.com", "roles": ["admin"]}],
                    }
                ),
            ]

            result = runner.invoke(app, ["grant", "remove", "myapi", "user@x.com"])

        assert result.exit_code == 0
        post_call = mock_client.request.call_args_list[1]
        body = post_call.kwargs.get("json") or post_call[1].get("json")
        subjects = [g["subject"] for g in body["grants"]]
        assert "user@x.com" not in subjects
        assert "other@x.com" in subjects


class TestGrantDelete:
    def test_deletes_service(self):
        with patch("dockmaster.cli.http.httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.request.return_value = _mock_response(status_code=204)

            result = runner.invoke(app, ["grant", "delete", "old-svc"])

        assert result.exit_code == 0
        assert "deleted" in result.output
