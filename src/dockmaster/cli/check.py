"""CLI command for permission checks."""

from __future__ import annotations

from typing import Annotated

import typer

from dockmaster.cli.http import api_request


def check_command(
    subject: str,
    target: Annotated[str, typer.Argument(help="Target service to check permission on")],
    permission: Annotated[str, typer.Option("-p", "--permission", help="Permission to check")],
):
    """Check if a subject has a permission on a target service."""
    data = api_request("GET", f"/auth/has/{subject}/{target}/{permission}")
    granted = data.get("granted", False)
    if granted:
        typer.echo("Oui!")
        raise typer.Exit(0)
    else:
        typer.echo("Non!")
        raise typer.Exit(1)
