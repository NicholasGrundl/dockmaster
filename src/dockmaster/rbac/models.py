"""RBAC data models — Role, Grant, ServiceGrants."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Role(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    permissions: list[str]


class Grant(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject: str
    roles: list[str]


class ServiceGrants(BaseModel):
    model_config = ConfigDict(extra="ignore")

    service: str
    grants: list[Grant]
