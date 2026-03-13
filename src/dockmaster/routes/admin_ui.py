"""Routes: Admin UI pages — /ui/roles, /ui/grants."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from google.api_core.exceptions import NotFound

from dockmaster.auth.admin import require_admin_ui, require_admin_writes
from dockmaster.rbac import admin_ops
from dockmaster.rbac.admin_ops import RoleConflictError
from dockmaster.rbac.models import Grant
from dockmaster.routes.ui import _ui_config, templates

router = APIRouter()


def _can_write(request: Request) -> bool:
    """Check if admin write operations are available (for template rendering)."""
    return getattr(request.app.state, "admin_storage", None) is not None


def _get_admin_storage(request: Request):
    return getattr(request.app.state, "admin_storage", None)


def _get_authority(request: Request):
    return getattr(request.app.state, "authority", None)


# ------------------------------------------------------------------
# Roles pages
# ------------------------------------------------------------------


@router.get("/roles", response_class=HTMLResponse)
async def roles_page(
    request: Request,
    user: dict = Depends(require_admin_ui),
):
    """List all roles with inline create form."""
    storage = _get_admin_storage(request)
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
            "can_write": _can_write(request),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/roles", response_class=HTMLResponse)
async def create_role_form(
    request: Request,
    user: dict = Depends(require_admin_ui),
    _: None = Depends(require_admin_writes),
    name: str = Form(...),
    permissions: str = Form(""),
):
    """Handle create role form submission."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)

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
    user: dict = Depends(require_admin_ui),
    _: None = Depends(require_admin_writes),
    permissions: str = Form(""),
):
    """Handle update role form submission."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)

    perm_list = [p.strip() for p in permissions.split(",") if p.strip()]
    await admin_ops.update_role(storage, authority, name, perm_list)

    return RedirectResponse(url="/ui/roles?success=Role+updated", status_code=303)


@router.post("/roles/{name}/delete", response_class=HTMLResponse)
async def delete_role_form(
    request: Request,
    name: str,
    user: dict = Depends(require_admin_ui),
    _: None = Depends(require_admin_writes),
):
    """Handle delete role form submission."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)

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
    user: dict = Depends(require_admin_ui),
):
    """List all services with grants."""
    storage = _get_admin_storage(request)
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
            "can_write": _can_write(request),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/grants/new", response_class=HTMLResponse)
async def create_service_grants_form(
    request: Request,
    user: dict = Depends(require_admin_ui),
    _: None = Depends(require_admin_writes),
    service: str = Form(...),
    subject: str = Form(...),
    roles: str = Form(""),
):
    """Handle create new service grants form submission."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)

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
    user: dict = Depends(require_admin_ui),
):
    """View/edit grants for a specific service."""
    storage = _get_admin_storage(request)
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
            "can_write": _can_write(request),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/grants/{service}", response_class=HTMLResponse)
async def update_grants_form(
    request: Request,
    service: str,
    user: dict = Depends(require_admin_ui),
    _: None = Depends(require_admin_writes),
):
    """Handle grants form submission — parses subject/roles pairs from form data."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)

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
    user: dict = Depends(require_admin_ui),
    _: None = Depends(require_admin_writes),
):
    """Handle delete all grants for a service."""
    storage = _get_admin_storage(request)
    authority = _get_authority(request)

    try:
        await admin_ops.delete_service_grants(storage, authority, service)
    except NotFound:
        return RedirectResponse(url=f"/ui/grants?error=Grants+for+'{service}'+not+found", status_code=303)

    return RedirectResponse(url="/ui/grants?success=Grants+deleted", status_code=303)
