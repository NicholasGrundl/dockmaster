"""CLI commands for grant management."""


from typing import Annotated

import typer

from dockmaster.cli.http import api_request, print_json

grant_app = typer.Typer(
    help="Manage RBAC service grants.\n\nUse -r/--role to specify roles on add and remove.",
    no_args_is_help=True,
)


@grant_app.command("list")
def grant_list():
    """List all services with grants."""
    data = api_request("GET", "/admin/grants")
    print_json(data)


@grant_app.command("get")
def grant_get(service: str):
    """Show all grants for a service."""
    data = api_request("GET", f"/admin/grants/{service}")
    print_json(data)


@grant_app.command("delete")
def grant_delete(service: str):
    """Delete a service and all its grants."""
    api_request("DELETE", f"/admin/grants/{service}")
    typer.echo(f"Service '{service}' grants deleted.")


@grant_app.command("add")
def grant_add(
    service: str,
    subject: str,
    role: Annotated[list[str], typer.Option("-r", "--role", help="Role to grant")] = [],
):
    """Add roles for a subject on a service."""
    if not role:
        typer.echo("Error: at least one --role/-r is required.", err=True)
        raise typer.Exit(1)

    # Fetch current grants (None if service doesn't exist yet), merge, put back
    current = api_request("GET", f"/admin/grants/{service}", allow_404=True)
    grants = current.get("grants", []) if current else []

    # Find existing grant for this subject or create new
    found = False
    for grant in grants:
        if grant["subject"] == subject:
            existing_roles = set(grant["roles"])
            grant["roles"] = list(existing_roles | set(role))
            found = True
            break

    if not found:
        grants.append({"subject": subject, "roles": list(role)})

    data = api_request("POST", f"/admin/grants/{service}", json_body={"grants": grants})
    print_json(data)


@grant_app.command("remove")
def grant_remove(
    service: str,
    subject: str,
    role: Annotated[list[str], typer.Option("-r", "--role", help="Specific role to remove (omit to remove all)")] = [],
):
    """Remove a subject's roles on a service. Omit --role to remove all."""
    current = api_request("GET", f"/admin/grants/{service}")
    grants = current.get("grants", [])

    if not role:
        # Remove entire subject
        grants = [g for g in grants if g["subject"] != subject]
    else:
        # Remove specific roles from subject
        for grant in grants:
            if grant["subject"] == subject:
                remaining = set(grant["roles"]) - set(role)
                if remaining:
                    grant["roles"] = list(remaining)
                else:
                    grants = [g for g in grants if g["subject"] != subject]
                break

    data = api_request("POST", f"/admin/grants/{service}", json_body={"grants": grants})
    print_json(data)
