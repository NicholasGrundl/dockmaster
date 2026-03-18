"""Routes: Admin UI pages — /ui/roles, /ui/grants, /ui/sessions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google.api_core.exceptions import NotFound

from dockmaster.auth.dependencies import (
    allow_session_admin,
    get_session_user,
    needs_admin_storage,
)
from dockmaster.rbac import admin_ops
from dockmaster.rbac.admin_ops import RoleConflictError
from dockmaster.rbac.authority import Authority
from dockmaster.rbac.models import Grant
from dockmaster.rbac.storage import AdminSecretsStorage
from dockmaster.routes.ui import _ui_config, templates
from dockmaster.sessions.protocol import SessionStore
from dockmaster.state import get_admin_storage, get_authority, get_session_store

router = APIRouter(
    tags=["admin-ui"],
    dependencies=[Depends(allow_session_admin)],
)


def _admin_writes_enabled(request: Request) -> bool:
    """Check if admin write operations are available (for template rendering)."""
    return getattr(request.app.state, "admin_storage", None) is not None


# ------------------------------------------------------------------
# Roles pages
# ------------------------------------------------------------------


@router.get("/roles", response_class=HTMLResponse)
async def roles_page(
    request: Request,
    user: Annotated[dict, Depends(get_session_user)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
):
    """List all roles with inline create form."""
    if storage:
        role_names = await admin_ops.list_roles(storage)
        roles = []
        for name in role_names:
            try:
                role = await admin_ops.get_role(storage, name)
                roles.append(role)
            except NotFound:
                pass
    else:
        # Read-only: try runtime storage
        runtime_storage = getattr(request.app.state, "secrets_storage", None)
        if runtime_storage:
            role_names = await admin_ops.list_roles(runtime_storage)
            roles = []
            for name in role_names:
                try:
                    role = await admin_ops.get_role(runtime_storage, name)
                    roles.append(role)
                except NotFound:
                    pass
        else:
            roles = []

    return templates.TemplateResponse(
        request,
        "roles.html",
        {
            "ui": _ui_config(request),
            "user": user,
            "roles": roles,
            "is_admin": True,
            "can_write": _admin_writes_enabled(request),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/roles", response_class=HTMLResponse)
async def create_role_form(
    request: Request,
    _: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
    name: str = Form(...),
    permissions: str = Form(""),
):
    """Handle create role form submission."""
    perm_list = [p.strip() for p in permissions.split(",") if p.strip()]

    try:
        await admin_ops.create_role(storage, authority, name.strip(), perm_list)
    except RoleConflictError:
        return RedirectResponse(url=f"/ui/roles?error=Role+'{name}'+already+exists", status_code=303)

    return RedirectResponse(url="/ui/roles?success=Role+created", status_code=303)


@router.post("/roles/{name}/update", response_class=HTMLResponse)
async def update_role_form(
    request: Request,
    name: str,
    _: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
    permissions: str = Form(""),
):
    """Handle update role form submission."""
    perm_list = [p.strip() for p in permissions.split(",") if p.strip()]
    await admin_ops.update_role(storage, authority, name, perm_list)

    return RedirectResponse(url="/ui/roles?success=Role+updated", status_code=303)


@router.post("/roles/{name}/delete", response_class=HTMLResponse)
async def delete_role_form(
    request: Request,
    name: str,
    _: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
):
    """Handle delete role form submission."""
    try:
        await admin_ops.delete_role(storage, authority, name)
    except NotFound:
        return RedirectResponse(url=f"/ui/roles?error=Role+'{name}'+not+found", status_code=303)

    return RedirectResponse(url="/ui/roles?success=Role+deleted", status_code=303)


# ------------------------------------------------------------------
# Grants pages
# ------------------------------------------------------------------


@router.get("/grants", response_class=HTMLResponse)
async def grants_page(
    request: Request,
    user: Annotated[dict, Depends(get_session_user)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
):
    """List all services with grants."""
    if not storage:
        storage = getattr(request.app.state, "secrets_storage", None)

    if storage:
        service_names = await admin_ops.list_service_grants(storage)
    else:
        service_names = []

    return templates.TemplateResponse(
        request,
        "grants.html",
        {
            "ui": _ui_config(request),
            "user": user,
            "service_names": service_names,
            "is_admin": True,
            "can_write": _admin_writes_enabled(request),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/grants/new", response_class=HTMLResponse)
async def create_service_grants_form(
    request: Request,
    _: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
    service: str = Form(...),
    subject: str = Form(...),
    roles: str = Form(""),
):
    """Handle create new service grants form submission."""
    service_name = service.strip()
    subject_email = subject.strip()
    role_list = [r.strip() for r in roles.split(",") if r.strip()]

    if not service_name or not subject_email or not role_list:
        return RedirectResponse(
            url="/ui/grants?error=Service,+subject,+and+roles+are+required",
            status_code=303,
        )

    grants = [Grant(subject=subject_email, roles=role_list)]
    await admin_ops.put_service_grants(storage, authority, service_name, grants)

    return RedirectResponse(
        url=f"/ui/grants/{service_name}?success=Service+grants+created",
        status_code=303,
    )


@router.get("/grants/{service}", response_class=HTMLResponse)
async def grants_detail_page(
    request: Request,
    service: str,
    user: Annotated[dict, Depends(get_session_user)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
):
    """View/edit grants for a specific service."""
    if not storage:
        storage = getattr(request.app.state, "secrets_storage", None)

    if not storage:
        raise HTTPException(status_code=503, detail="Storage not configured")

    try:
        sg = await admin_ops.get_service_grants(storage, service)
    except NotFound:
        raise HTTPException(status_code=404, detail=f"Grants for '{service}' not found")

    return templates.TemplateResponse(
        request,
        "grants_detail.html",
        {
            "ui": _ui_config(request),
            "user": user,
            "service_grants": sg,
            "is_admin": True,
            "can_write": _admin_writes_enabled(request),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/grants/{service}", response_class=HTMLResponse)
async def update_grants_form(
    request: Request,
    service: str,
    _: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
):
    """Handle grants form submission — parses subject/roles pairs from form data."""
    form_data = await request.form()

    # Parse grants from form: subject_0, roles_0, subject_1, roles_1, ...
    grants = []
    i = 0
    while f"subject_{i}" in form_data:
        subject = form_data[f"subject_{i}"].strip()
        roles_str = form_data.get(f"roles_{i}", "")
        roles = [r.strip() for r in roles_str.split(",") if r.strip()]
        if subject and roles:
            grants.append(Grant(subject=subject, roles=roles))
        i += 1

    # Also check for new grant
    new_subject = form_data.get("new_subject", "").strip()
    new_roles_str = form_data.get("new_roles", "")
    new_roles = [r.strip() for r in new_roles_str.split(",") if r.strip()]
    if new_subject and new_roles:
        grants.append(Grant(subject=new_subject, roles=new_roles))

    await admin_ops.put_service_grants(storage, authority, service, grants)

    return RedirectResponse(url=f"/ui/grants/{service}?success=Grants+updated", status_code=303)


@router.post("/grants/{service}/delete", response_class=HTMLResponse)
async def delete_grants_form(
    request: Request,
    service: str,
    _: Annotated[None, Depends(needs_admin_storage)],
    storage: Annotated[AdminSecretsStorage | None, Depends(get_admin_storage)],
    authority: Annotated[Authority | None, Depends(get_authority)],
):
    """Handle delete all grants for a service."""
    try:
        await admin_ops.delete_service_grants(storage, authority, service)
    except NotFound:
        return RedirectResponse(url=f"/ui/grants?error=Grants+for+'{service}'+not+found", status_code=303)

    return RedirectResponse(url="/ui/grants?success=Grants+deleted", status_code=303)


# ------------------------------------------------------------------
# Sessions pages
# ------------------------------------------------------------------


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_page(
    request: Request,
    user: Annotated[dict, Depends(get_session_user)],
    store: Annotated[SessionStore | None, Depends(get_session_store)],
):
    """List all active sessions with revoke controls."""
    sessions = await admin_ops.list_sessions(store) if store else {}

    return templates.TemplateResponse(
        request,
        "sessions.html",
        {
            "ui": _ui_config(request),
            "user": user,
            "sessions": sessions,
            "is_admin": True,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/sessions/{session_id}/revoke", response_class=HTMLResponse)
async def revoke_session_form(
    request: Request,
    session_id: str,
    store: Annotated[SessionStore | None, Depends(get_session_store)],
):
    """Handle revoke single session form submission."""
    if not store:
        return RedirectResponse(url="/ui/sessions?error=Session+store+not+configured", status_code=303)

    revoked = await admin_ops.revoke_session(store, session_id)
    if not revoked:
        return RedirectResponse(url="/ui/sessions?error=Session+not+found", status_code=303)

    return RedirectResponse(url="/ui/sessions?success=Session+revoked", status_code=303)


@router.post("/sessions/revoke-by-email", response_class=HTMLResponse)
async def revoke_sessions_by_email_form(
    request: Request,
    store: Annotated[SessionStore | None, Depends(get_session_store)],
    email: str = Form(...),
):
    """Handle revoke all sessions for an email form submission."""
    if not store:
        return RedirectResponse(url="/ui/sessions?error=Session+store+not+configured", status_code=303)

    count = await admin_ops.revoke_sessions_by_email(store, email.strip())

    return RedirectResponse(
        url=f"/ui/sessions?success={count}+session(s)+revoked+for+{email.strip()}",
        status_code=303,
    )
