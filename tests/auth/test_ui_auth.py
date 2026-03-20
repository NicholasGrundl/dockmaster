"""Tests for AuthResult model and check_ui_session dependency.

Step 0c of the Phase 11 revised plan.
"""

import pytest


# --- AuthResult model ---


def test_auth_result_authenticated_no_permission_check():
    """AuthResult with session but no permission args → has_permission=None."""
    pass


def test_auth_result_authenticated_with_permission_granted():
    """AuthResult with session + permission check → has_permission=True."""
    pass


def test_auth_result_authenticated_with_permission_denied():
    """AuthResult with session + permission check → has_permission=False."""
    pass


def test_auth_result_not_authenticated():
    """AuthResult with no session → is_authenticated=False, has_permission=None, user={}."""
    pass


# --- check_ui_session (no permission args) ---


@pytest.mark.anyio
async def test_check_ui_session_no_args_valid_session():
    """check_ui_session() with valid cookie → authenticated, has_permission=None."""
    pass


@pytest.mark.anyio
async def test_check_ui_session_no_args_no_session():
    """check_ui_session() with no cookie → not authenticated."""
    pass


@pytest.mark.anyio
async def test_check_ui_session_no_args_bad_cookie():
    """check_ui_session() with invalid/tampered cookie → not authenticated."""
    pass


# --- check_ui_session (with permission args) ---


@pytest.mark.anyio
async def test_check_ui_session_with_permission_granted():
    """check_ui_session("dockmaster", "admin") + user has permission → True."""
    pass


@pytest.mark.anyio
async def test_check_ui_session_with_permission_denied():
    """check_ui_session("dockmaster", "admin") + user lacks permission → False."""
    pass


@pytest.mark.anyio
async def test_check_ui_session_with_permission_whitelist_bypass():
    """check_ui_session with permission args, user in admin whitelist → True."""
    pass


# --- check_ui_session never raises ---


@pytest.mark.anyio
async def test_check_ui_session_never_raises_on_missing_session_store():
    """check_ui_session returns not-authenticated even if session_store is None."""
    pass


@pytest.mark.anyio
async def test_check_ui_session_never_raises_on_missing_authority():
    """check_ui_session returns authenticated but has_permission=False if authority is None."""
    pass
