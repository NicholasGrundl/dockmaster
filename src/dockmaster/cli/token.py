"""CLI command: dockmaster token <service> — get a Type C JWT for a service."""


import httpx
import typer

from dockmaster.cli.auth import require_token
from dockmaster.cli.config import get_server_url


def token_command(
    service: str = typer.Argument(help="Target service to get a token for"),
) -> None:
    """Request a Type C JWT for a target service and print it to stdout."""
    cli_token = require_token()
    server_url = get_server_url()

    with httpx.Client(base_url=server_url, timeout=30) as client:
        response = client.post(
            "/auth/token",
            params={"service": service},
            headers={"Authorization": f"Bearer {cli_token}"},
        )

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        typer.echo(f"Error ({response.status_code}): {detail}", err=True)
        raise typer.Exit(1)

    data = response.json()
    # Print just the token to stdout (pipeable)
    typer.echo(data["access_token"])
