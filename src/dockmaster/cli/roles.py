"""CLI commands for role management."""


from typing import Annotated

import typer

from dockmaster.cli.http import api_request, print_json

role_app = typer.Typer(
    help="Manage RBAC roles.\n\nUse -p/--permission to specify permissions on create, add, and remove.",
    no_args_is_help=True,
)


@role_app.command("list")
def role_list():
    """List all roles."""
    data = api_request("GET", "/admin/roles")
    print_json(data)


@role_app.command("get")
def role_get(name: str):
    """Show a role and its permissions."""
    data = api_request("GET", f"/admin/roles/{name}")
    print_json(data)


@role_app.command("create")
def role_create(
    name: str,
    permission: Annotated[list[str], typer.Option("-p", "--permission", help="Permission to include")] = [],
):
    """Create a role with permissions."""
    if not permission:
        typer.echo("Error: at least one --permission/-p is required.", err=True)
        raise typer.Exit(1)
    data = api_request("POST", "/admin/roles", json_body={"name": name, "permissions": permission})
    print_json(data)


@role_app.command("delete")
def role_delete(name: str):
    """Delete a role."""
    api_request("DELETE", f"/admin/roles/{name}")
    typer.echo(f"Role '{name}' deleted.")


@role_app.command("add")
def role_add(
    name: str,
    permission: Annotated[list[str], typer.Option("-p", "--permission", help="Permission to add")] = [],
):
    """Add permissions to an existing role."""
    if not permission:
        typer.echo("Error: at least one --permission/-p is required.", err=True)
        raise typer.Exit(1)
    # Fetch current role, merge permissions, update
    current = api_request("GET", f"/admin/roles/{name}")
    existing = set(current.get("permissions", []))
    merged = list(existing | set(permission))
    data = api_request("PUT", f"/admin/roles/{name}", json_body={"permissions": merged})
    print_json(data)


@role_app.command("remove")
def role_remove(
    name: str,
    permission: Annotated[list[str], typer.Option("-p", "--permission", help="Permission to remove")] = [],
):
    """Remove permissions from an existing role."""
    if not permission:
        typer.echo("Error: at least one --permission/-p is required.", err=True)
        raise typer.Exit(1)
    # Fetch current role, remove permissions, update
    current = api_request("GET", f"/admin/roles/{name}")
    existing = set(current.get("permissions", []))
    remaining = list(existing - set(permission))
    data = api_request("PUT", f"/admin/roles/{name}", json_body={"permissions": remaining})
    print_json(data)
