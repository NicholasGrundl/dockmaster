"""Tests for RBAC Pydantic models — Role, Grant, ServiceGrants."""

from __future__ import annotations

import json

from dockmaster.rbac.models import Grant, Role, ServiceGrants


class TestRole:
    def test_basic_validation(self):
        role = Role(name="viewer", permissions=["read", "list"])
        assert role.name == "viewer"
        assert role.permissions == ["read", "list"]

    def test_extra_fields_ignored(self):
        """Legacy secrets may include a 'kind' field — must be silently ignored."""
        role = Role(name="editor", permissions=["read", "write"], kind="Role")
        assert role.name == "editor"
        assert not hasattr(role, "kind")

    def test_empty_permissions(self):
        role = Role(name="noop", permissions=[])
        assert role.permissions == []

    def test_from_fixture(self, fixtures_dir):
        data = json.loads((fixtures_dir / "rbac" / "role_viewer.json").read_text())
        role = Role.model_validate(data)
        assert role.name == "viewer"
        assert "read" in role.permissions


class TestGrant:
    def test_basic_validation(self):
        grant = Grant(subject="alice@example.com", roles=["viewer"])
        assert grant.subject == "alice@example.com"
        assert grant.roles == ["viewer"]

    def test_multiple_roles(self):
        grant = Grant(subject="alice@example.com", roles=["viewer", "editor"])
        assert len(grant.roles) == 2

    def test_service_account_subject(self):
        grant = Grant(subject="sa@project.iam.gserviceaccount.com", roles=["admin"])
        assert "iam.gserviceaccount.com" in grant.subject

    def test_extra_fields_ignored(self):
        grant = Grant(subject="a@b.com", roles=["viewer"], kind="Grant")
        assert not hasattr(grant, "kind")


class TestServiceGrants:
    def test_basic_validation(self):
        sg = ServiceGrants(
            service="data-pipeline",
            grants=[Grant(subject="alice@example.com", roles=["viewer"])],
        )
        assert sg.service == "data-pipeline"
        assert len(sg.grants) == 1

    def test_from_fixture(self, fixtures_dir):
        data = json.loads((fixtures_dir / "rbac" / "service_grants_example.json").read_text())
        sg = ServiceGrants.model_validate(data)
        assert sg.service == "data-pipeline"
        assert len(sg.grants) == 3
        assert sg.grants[0].subject == "alice@example.com"
        assert sg.grants[0].roles == ["viewer", "editor"]

    def test_serialization_roundtrip(self):
        sg = ServiceGrants(
            service="my-service",
            grants=[
                Grant(subject="a@b.com", roles=["viewer", "editor"]),
                Grant(subject="c@d.com", roles=["admin"]),
            ],
        )
        data = sg.model_dump()
        sg2 = ServiceGrants.model_validate(data)
        assert sg2 == sg

    def test_extra_fields_ignored(self):
        sg = ServiceGrants(
            service="svc",
            grants=[],
            kind="ServiceGrants",
        )
        assert not hasattr(sg, "kind")
