"""Tests for dockmaster configuration."""

from dockmaster.config import Settings, create_settings


class TestSettingsDefaults:
    """Test that Settings has correct defaults when no env vars are set."""

    def test_defaults(self, monkeypatch):
        """All defaults should be sensible when no env vars are provided."""
        # Clear any env vars that might interfere
        for var in [
            "SA_KEY_FILE",
            "ADMIN_SA_KEY_FILE",
            "SECRETS_PROJECT",
            "LOG_LEVEL",
            "AUTHORIZED_ISSUERS",
            "AUTHORIZED_DOMAINS",
            "AUTHORIZED_AUDIENCE",
            "CLIENT_ID",
            "CLIENT_SECRET",
            "DEFAULT_CLIENT_ID",
            "CLIENT_ID_SUFFIX",
            "ACCESS_TOKEN_ENDPOINT",
            "REFRESH_TOKEN_ENDPOINT",
            "USERINFO_ENDPOINT",
            "REDIS_URL",
            "SESSION_SECRET_KEY",
            "DOCKMASTER_ADMIN_EMAILS",
            "DOCKMASTER_TOKEN_TTL",
            "ALLOWED_REDIRECT_URIS",
            "ALLOWED_ORIGINS",
            "JWKS_REGISTRY_PATH",
        ]:
            monkeypatch.delenv(var, raising=False)

        settings = Settings(_env_file=None)

        # Service defaults
        assert settings.sa_key_file is None
        assert settings.secrets_project is None
        assert settings.log_level == "INFO"

        # Authorization defaults (empty sets)
        assert settings.authorized_issuers == set()
        assert settings.authorized_domains == set()
        assert settings.authorized_audience == set()

        # OAuth defaults
        assert settings.client_id is None
        assert settings.client_secret is None
        assert settings.client_id_suffix == ".apps.googleusercontent.com"

        # Google endpoint defaults
        assert settings.access_token_endpoint == "https://oauth2.googleapis.com/tokeninfo"
        assert settings.userinfo_endpoint == "https://www.googleapis.com/oauth2/v3/userinfo"

        # Admin defaults
        assert settings.admin_sa_key_file is None
        assert settings.dockmaster_admin_emails == set()

        # Session defaults
        assert settings.redis_url is None
        assert isinstance(settings.session_secret_key, str)
        assert len(settings.session_secret_key) > 0  # auto-generated


class TestCommaSeparatedParsing:
    """Test that comma-separated env vars are parsed into sets."""

    def test_comma_separated_parsing(self):
        settings = Settings(authorized_issuers="a,b,c")
        assert settings.authorized_issuers == {"a", "b", "c"}

    def test_comma_separated_with_whitespace(self):
        settings = Settings(authorized_domains=" a , b ")
        assert settings.authorized_domains == {"a", "b"}

    def test_comma_separated_empty_string(self):
        settings = Settings(authorized_issuers="")
        assert settings.authorized_issuers == set()

    def test_comma_separated_none(self, monkeypatch):
        monkeypatch.delenv("AUTHORIZED_ISSUERS", raising=False)
        settings = Settings(authorized_issuers="")
        assert settings.authorized_issuers == set()

    def test_comma_separated_single_value(self):
        settings = Settings(authorized_audience="https://accounts.google.com")
        assert settings.authorized_audience == {"https://accounts.google.com"}

    def test_comma_separated_from_env(self, monkeypatch):
        monkeypatch.setenv("AUTHORIZED_ISSUERS", "x,y,z")
        settings = Settings()
        assert settings.authorized_issuers == {"x", "y", "z"}

    def test_comma_separated_accepts_set(self):
        settings = Settings(authorized_issuers={"already", "a", "set"})
        assert settings.authorized_issuers == {"already", "a", "set"}

    def test_comma_separated_accepts_list(self):
        settings = Settings(authorized_domains=["a", "b"])
        assert settings.authorized_domains == {"a", "b"}


class TestAdminSettings:
    """Test admin-specific settings."""

    def test_admin_sa_key_file_default(self):
        settings = Settings(admin_sa_key_file=None, _env_file=None)
        assert settings.admin_sa_key_file is None

    def test_admin_sa_key_file_set(self):
        settings = Settings(admin_sa_key_file="secrets/admin.json", _env_file=None)
        assert settings.admin_sa_key_file == "secrets/admin.json"

    def test_admin_emails_comma_separated(self):
        settings = Settings(dockmaster_admin_emails="a@co.com,b@co.com", _env_file=None)
        assert settings.dockmaster_admin_emails == {"a@co.com", "b@co.com"}

    def test_admin_emails_empty_default(self, monkeypatch):
        monkeypatch.delenv("DOCKMASTER_ADMIN_EMAILS", raising=False)
        settings = Settings(_env_file=None)
        assert settings.dockmaster_admin_emails == set()

    def test_admin_emails_single(self):
        settings = Settings(dockmaster_admin_emails="admin@co.com", _env_file=None)
        assert settings.dockmaster_admin_emails == {"admin@co.com"}

    def test_admin_emails_from_env(self, monkeypatch):
        monkeypatch.setenv("DOCKMASTER_ADMIN_EMAILS", "x@co.com, y@co.com")
        settings = Settings(_env_file=None)
        assert settings.dockmaster_admin_emails == {"x@co.com", "y@co.com"}


class TestLogLevel:
    """Test log level normalization."""

    def test_log_level_normalized_to_uppercase(self):
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"

    def test_log_level_already_uppercase(self):
        settings = Settings(log_level="WARNING")
        assert settings.log_level == "WARNING"


class TestClientSecret:
    """Test that client_secret uses SecretStr."""

    def test_client_secret_is_secret_str(self):
        settings = Settings(client_secret="mysecret")
        assert settings.client_secret is not None
        assert settings.client_secret.get_secret_value() == "mysecret"
        assert "mysecret" not in str(settings.client_secret)
        assert "mysecret" not in repr(settings.client_secret)


class TestPhase7Settings:
    """Test Phase 7 settings: token TTL, redirect URIs, CORS origins, JWKS registry path."""

    def test_dockmaster_token_ttl_default(self):
        settings = Settings(_env_file=None)
        assert settings.dockmaster_token_ttl == 900

    def test_dockmaster_token_ttl_custom(self):
        settings = Settings(dockmaster_token_ttl=3600, _env_file=None)
        assert settings.dockmaster_token_ttl == 3600

    def test_dockmaster_token_ttl_from_env(self, monkeypatch):
        monkeypatch.setenv("DOCKMASTER_TOKEN_TTL", "1800")
        settings = Settings(_env_file=None)
        assert settings.dockmaster_token_ttl == 1800

    def test_allowed_redirect_uris_default_empty(self):
        settings = Settings(allowed_redirect_uris="", _env_file=None)
        assert settings.allowed_redirect_uris == set()

    def test_allowed_redirect_uris_comma_separated(self):
        settings = Settings(
            allowed_redirect_uris="https://app.example.com/callback,https://other.com/cb",
            _env_file=None,
        )
        assert settings.allowed_redirect_uris == {
            "https://app.example.com/callback",
            "https://other.com/cb",
        }

    def test_allowed_redirect_uris_from_env(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_REDIRECT_URIS", "https://a.com/cb, https://b.com/cb")
        settings = Settings(_env_file=None)
        assert settings.allowed_redirect_uris == {"https://a.com/cb", "https://b.com/cb"}

    def test_allowed_origins_default_empty(self):
        settings = Settings(allowed_origins="", _env_file=None)
        assert settings.allowed_origins == set()

    def test_allowed_origins_comma_separated(self):
        settings = Settings(allowed_origins="https://app.example.com,https://other.com", _env_file=None)
        assert settings.allowed_origins == {"https://app.example.com", "https://other.com"}

    def test_allowed_origins_from_env(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.com, https://b.com")
        settings = Settings(_env_file=None)
        assert settings.allowed_origins == {"https://a.com", "https://b.com"}

    def test_jwks_registry_path_default_none(self):
        settings = Settings(_env_file=None)
        assert settings.jwks_registry_path is None

    def test_jwks_registry_path_custom(self):
        settings = Settings(jwks_registry_path="/tmp/jwks.json", _env_file=None)
        assert settings.jwks_registry_path == "/tmp/jwks.json"


class TestCreateSettings:
    """Test the create_settings() factory function."""

    def test_create_settings_returns_settings(self):
        result = create_settings()
        assert isinstance(result, Settings)

    def test_create_settings_returns_fresh_instance(self):
        first = create_settings()
        second = create_settings()
        assert first is not second
        assert first.log_level == second.log_level
