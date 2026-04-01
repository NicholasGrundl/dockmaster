"""Dockmaster CLI — Typer app entry point."""

from __future__ import annotations

import typer

from dockmaster.cli.auth import login_command, logout_command
from dockmaster.cli.check import check_command
from dockmaster.cli.grants import grant_app
from dockmaster.cli.roles import role_app
from dockmaster.cli.token import token_command

app = typer.Typer(
    name="dockmaster",
    help="CLI for managing Dockmaster RBAC roles and grants.",
    no_args_is_help=True,
)

# Sub-command groups
app.add_typer(role_app, name="role")
app.add_typer(grant_app, name="grant")

# Top-level commands
app.command("login")(login_command)
app.command("logout")(logout_command)
app.command("check")(check_command)
app.command("token")(token_command)
