"""Dockmaster service configuration via pydantic-settings."""

from functools import lru_cache
from typing import Any

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_comma_separated(v: Any) -> set[str]:
    """Parse a comma-separated string into a set of stripped strings."""
    if v is None or v == "":
        return set()
    if isinstance(v, (set, frozenset)):
        return set(v)
    if isinstance(v, list):
        return set(v)
    if isinstance(v, str):
        return {s.strip() for s in v.split(",") if s.strip()}
    return set()


class Settings(BaseSettings):
    """Dockmaster service settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Service ---
    sa_key_file: str | None = None
    secrets_project: str | None = None
    log_level: str = "INFO"

    # --- Authorization ---
    # Typed as str to prevent pydantic-settings from attempting JSON decode on env vars.
    # Converted to set[str] in model_validator(mode="after").
    authorized_issuers: str | set[str] = ""
    authorized_domains: str | set[str] = ""
    authorized_audience: str | set[str] = ""

    # --- OAuth ---
    client_id: str | None = None
    client_secret: SecretStr | None = None
    default_client_id: str | None = None
    client_id_suffix: str = ".apps.googleusercontent.com"

    # --- Google Endpoints ---
    access_token_endpoint: str = "https://oauth2.googleapis.com/tokeninfo"
    refresh_token_endpoint: str = "https://www.googleapis.com/oauth2/v4/token"
    userinfo_endpoint: str = "https://www.googleapis.com/oauth2/v3/userinfo"

    # --- UI ---
    ui_config_path: str | None = None

    # --- RBAC ---
    rbac_cache_ttl: int = 300

    # --- Dockmaster Token Issuance (Phase 7) ---
    dockmaster_token_ttl: int = 900
    allowed_redirect_uris: str | set[str] = ""
    allowed_origins: str | set[str] = ""
    jwks_registry_path: str | None = None

    # --- Admin ---
    admin_sa_key_file: str | None = None
    dockmaster_admin_emails: str | set[str] = ""

    # --- Session ---
    redis_url: str | None = None
    session_secret_key: str = "change-me-in-production"
    session_ttl: int = 3600

    @model_validator(mode="after")
    def postprocess(self) -> "Settings":
        # Parse comma-separated authorization fields into sets
        for field in ("authorized_issuers", "authorized_domains", "authorized_audience", "dockmaster_admin_emails", "allowed_redirect_uris", "allowed_origins"):
            raw = getattr(self, field)
            parsed = _parse_comma_separated(raw)
            object.__setattr__(self, field, parsed)

        # Normalize log_level to uppercase
        if isinstance(self.log_level, str):
            object.__setattr__(self, "log_level", self.log_level.upper())

        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Override in tests via dependency_overrides."""
    return Settings()
