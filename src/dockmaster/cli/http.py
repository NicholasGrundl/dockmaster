"""Shared HTTP client for CLI commands."""

from __future__ import annotations

import json

import httpx
import typer

from dockmaster.cli.auth import require_token
from dockmaster.cli.config import get_server_url


def _client() -> httpx.Client:
    """Create an authenticated httpx client."""
    token = require_token()
    return httpx.Client(
        base_url=get_server_url(),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )


def api_request(method: str, path: str, json_body: dict | None = None) -> dict:
    """Make an authenticated API request and return the JSON response.

    Exits with code 1 on HTTP errors.
    """
    with _client() as client:
        response = client.request(method, path, json=json_body)

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        typer.echo(f"Error ({response.status_code}): {detail}", err=True)
        raise typer.Exit(1)

    if response.status_code == 204 or not response.content:
        return {}

    return response.json()


def print_json(data: dict | list) -> None:
    """Pretty-print JSON data to stdout."""
    typer.echo(json.dumps(data, indent=2))
