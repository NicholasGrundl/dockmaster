"""Tests for dockmaster configuration."""

from dockmaster.config import Settings, get_settings


class TestSettingsDefaults:
    """Test that Settings has correct defaults when no env vars are set."""

    def test_defaults(self, monkeypatch):
        """All defaults should be sensible when no env vars are provided."""
        # Clear any env vars that might interfere
        for var in [
            "ISSUER",
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
        ]:
            monkeypatch.delenv(var, raising=False)

        settings = Settings(_env_file=None)

        # Service defaults
        assert settings.issuer is None
        assert settings.secrets_project is None
        assert settings.log_level == "INFO"

        # Authorization defaults (empty sets)
        assert settings.authorized_issuers == set()
        assert settings.authorized_domains == set()
        assert settings.authorized_audience == set()

        # OAuth defaults
        assert settings.client_id is None
        assert settings.client_secret is None
        assert settings.default_client_id is None
        assert settings.client_id_suffix == ".apps.googleusercontent.com"

        # Google endpoint defaults
        assert settings.access_token_endpoint == "https://oauth2.googleapis.com/tokeninfo"
        assert settings.refresh_token_endpoint == "https://www.googleapis.com/oauth2/v4/token"
        assert settings.userinfo_endpoint == "https://www.googleapis.com/oauth2/v3/userinfo"

        # Session defaults
        assert settings.redis_url is None
        assert settings.session_secret_key == "change-me-in-production"


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


class TestGetSettings:
    """Test the get_settings() caching function."""

    def test_get_settings_returns_settings(self):
        result = get_settings()
        assert isinstance(result, Settings)

    def test_get_settings_caching(self):
        get_settings.cache_clear()
        first = get_settings()
        second = get_settings()
        assert first is second
