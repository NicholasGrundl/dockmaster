"""Tests for KeyCache base class (TTL logic only, no GCP)."""

import time

import pytest

from dockmaster.auth.key_cache import KeyCache, ServiceAccountKeyCache


class TrackingKeyCache(KeyCache):
    """KeyCache subclass that counts update() calls."""

    def __init__(self, keys: dict[str, str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._staged_keys = keys or {}
        self.update_count = 0

    def update(self) -> None:
        self.update_count += 1
        self._keys = dict(self._staged_keys)
        self._updated_at = time.time()


class TestKeyCacheInit:
    def test_starts_empty(self):
        cache = KeyCache()
        assert cache.get_all_keys() == {}

    def test_starts_expired(self):
        cache = KeyCache(expiry=300)
        assert cache._is_expired() is True


class TestKeyCacheTTL:
    def test_not_expired_after_update(self):
        cache = TrackingKeyCache(expiry=300)
        cache.update()
        assert cache._is_expired() is False

    def test_expired_after_ttl(self):
        cache = TrackingKeyCache(expiry=0)
        cache.update()
        # expiry=0 means it's always expired
        assert cache._is_expired() is True


class TestGetKey:
    def test_get_key_triggers_update_when_expired(self):
        cache = TrackingKeyCache(keys={"k1": "pem1"}, expiry=300)
        assert cache.update_count == 0
        result = cache.get_key("k1")
        assert result == "pem1"
        assert cache.update_count == 1

    def test_get_key_does_not_update_when_fresh(self):
        cache = TrackingKeyCache(keys={"k1": "pem1"}, expiry=300)
        cache.update()  # make it fresh
        assert cache.update_count == 1
        cache.get_key("k1")
        assert cache.update_count == 1  # no additional update

    def test_get_key_returns_none_for_unknown_kid(self):
        cache = TrackingKeyCache(keys={"k1": "pem1"}, expiry=300)
        assert cache.get_key("unknown") is None

    def test_get_all_keys_returns_copy(self):
        cache = TrackingKeyCache(keys={"k1": "pem1", "k2": "pem2"}, expiry=300)
        cache.update()
        all_keys = cache.get_all_keys()
        assert all_keys == {"k1": "pem1", "k2": "pem2"}
        # Modifying returned dict shouldn't affect cache
        all_keys["k3"] = "pem3"
        assert "k3" not in cache.get_all_keys()


class TestBaseUpdateIsNoop:
    def test_base_update_does_not_raise(self):
        cache = KeyCache()
        cache.update()  # should be a no-op


# ---------------------------------------------------------------------------
# ServiceAccountKeyCache
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_iam(mocker):
    """Mock googleapiclient IAM service."""
    mock = mocker.MagicMock()
    mocker.patch("dockmaster.auth.key_cache.build", return_value=mock)
    mocker.patch("dockmaster.auth.key_cache.service_account")
    return mock


def _wire_iam(mock_iam, sa_list_body, keys_body, key_body):
    """Wire mock IAM responses for a single SA with a single key."""
    mock_sa = mock_iam.projects.return_value.serviceAccounts.return_value
    mock_sa.list.return_value.execute.return_value = sa_list_body
    mock_sa.list_next.return_value = None
    mock_sa.keys.return_value.list.return_value.execute.return_value = keys_body
    mock_sa.keys.return_value.get.return_value.execute.return_value = key_body


class TestServiceAccountKeyCacheInit:
    def test_accepts_dict_credentials(self, fake_sa_key_data):
        cache = ServiceAccountKeyCache(credentials=fake_sa_key_data)
        assert cache._project == "test-project"

    def test_accepts_string_path(self, fake_sa_key_path):
        cache = ServiceAccountKeyCache(credentials=str(fake_sa_key_path))
        assert cache._project == "test-project"

    def test_project_override(self, fake_sa_key_data):
        cache = ServiceAccountKeyCache(credentials=fake_sa_key_data, project="other-project")
        assert cache._project == "other-project"

    def test_starts_expired(self, fake_sa_key_data):
        cache = ServiceAccountKeyCache(credentials=fake_sa_key_data)
        assert cache._is_expired() is True


class TestServiceAccountKeyCacheUpdate:
    def test_loads_oidc_and_sa_keys(
        self,
        mocker,
        mock_iam,
        fake_sa_key_data,
        google_oidc_certs,
        iam_list_service_accounts,
        iam_list_keys_sa0,
        iam_get_public_key_sa0_key0,
    ):
        oidc_body = google_oidc_certs["response"]["body"]
        mock_resp = mocker.MagicMock()
        mock_resp.json.return_value = oidc_body
        mocker.patch("dockmaster.auth.key_cache.httpx.get", return_value=mock_resp)

        _wire_iam(
            mock_iam,
            sa_list_body=iam_list_service_accounts["response"]["body"],
            keys_body=iam_list_keys_sa0["response"]["body"],
            key_body=iam_get_public_key_sa0_key0["response"]["body"],
        )

        cache = ServiceAccountKeyCache(credentials=fake_sa_key_data)
        cache.update()

        # OIDC kids present
        for kid in oidc_body:
            assert kid in cache._keys

        # SA key present — kid is the last segment of the key name
        key_name = iam_list_keys_sa0["response"]["body"]["keys"][0]["name"]
        sa_kid = key_name.split("/")[-1]
        assert sa_kid in cache._keys

        # SA PEM is a real certificate
        assert "BEGIN CERTIFICATE" in cache._keys[sa_kid]

    def test_not_expired_after_update(
        self,
        mocker,
        mock_iam,
        fake_sa_key_data,
        google_oidc_certs,
        iam_list_service_accounts,
        iam_list_keys_sa0,
        iam_get_public_key_sa0_key0,
    ):
        mock_resp = mocker.MagicMock()
        mock_resp.json.return_value = google_oidc_certs["response"]["body"]
        mocker.patch("dockmaster.auth.key_cache.httpx.get", return_value=mock_resp)
        _wire_iam(
            mock_iam,
            iam_list_service_accounts["response"]["body"],
            iam_list_keys_sa0["response"]["body"],
            iam_get_public_key_sa0_key0["response"]["body"],
        )

        cache = ServiceAccountKeyCache(credentials=fake_sa_key_data)
        cache.update()
        assert cache._is_expired() is False

    def test_oidc_failure_is_nonfatal(
        self,
        mocker,
        mock_iam,
        fake_sa_key_data,
        iam_list_service_accounts,
        iam_list_keys_sa0,
        iam_get_public_key_sa0_key0,
    ):
        mocker.patch(
            "dockmaster.auth.key_cache.httpx.get", side_effect=Exception("network error")
        )
        _wire_iam(
            mock_iam,
            iam_list_service_accounts["response"]["body"],
            iam_list_keys_sa0["response"]["body"],
            iam_get_public_key_sa0_key0["response"]["body"],
        )

        cache = ServiceAccountKeyCache(credentials=fake_sa_key_data)
        cache.update()  # must not raise

        # SA key still loaded despite OIDC failure
        key_name = iam_list_keys_sa0["response"]["body"]["keys"][0]["name"]
        sa_kid = key_name.split("/")[-1]
        assert sa_kid in cache._keys

    def test_iam_failure_is_nonfatal(
        self,
        mocker,
        fake_sa_key_data,
        google_oidc_certs,
    ):
        oidc_body = google_oidc_certs["response"]["body"]
        mock_resp = mocker.MagicMock()
        mock_resp.json.return_value = oidc_body
        mocker.patch("dockmaster.auth.key_cache.httpx.get", return_value=mock_resp)
        mocker.patch(
            "dockmaster.auth.key_cache.build", side_effect=Exception("IAM unavailable")
        )
        mocker.patch("dockmaster.auth.key_cache.service_account")

        cache = ServiceAccountKeyCache(credentials=fake_sa_key_data)
        cache.update()  # must not raise

        # OIDC keys still loaded despite IAM failure
        for kid in oidc_body:
            assert kid in cache._keys
