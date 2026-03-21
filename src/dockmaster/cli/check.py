"""CLI command for permission checks."""

from typing import Annotated

import httpx
import typer

from dockmaster.cli.auth import require_token
from dockmaster.cli.config import get_server_url


def check_command(
    subject: str,
    target: Annotated[str, typer.Argument(help="Target service to check permission on")],
    permission: Annotated[str, typer.Option("-p", "--permission", help="Permission to check")],
):
    """Check if a subject has a permission on a target service."""
    token = require_token()
    with httpx.Client(
        base_url=get_server_url(),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    ) as client:
        response = client.get(f"/auth/has/{subject}/{target}/{permission}")

    if response.status_code == 204:
        typer.echo("Oui!")
        raise typer.Exit(0)
    elif response.status_code == 403:
        typer.echo("Non!")
        raise typer.Exit(1)
    else:
        typer.echo(f"Error ({response.status_code}): {response.text}", err=True)
        raise typer.Exit(1)
