import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.config import Settings
from app.core.security import get_current_user
from app.core.startup import ConfigurationError, validate_configuration


def _settings(monkeypatch, **env: str) -> Settings:
    monkeypatch.delenv("AUTH_MOCK_MODE", raising=False)
    monkeypatch.delenv("MOCK_AUTH", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_mock_auth_is_off_by_default(monkeypatch):
    settings = _settings(monkeypatch)
    assert settings.app_env == "development"
    assert settings.auth_mock_mode is False


def test_mock_auth_turns_on_only_when_asked(monkeypatch):
    assert _settings(monkeypatch, MOCK_AUTH="1", APP_ENV="development").auth_mock_mode is True
    assert _settings(monkeypatch, MOCK_AUTH="yes", APP_ENV="test").auth_mock_mode is True
    assert _settings(monkeypatch, MOCK_AUTH="yes", APP_ENV="staging").auth_mock_mode is False
    assert _settings(monkeypatch, MOCK_AUTH="0").auth_mock_mode is False
    assert _settings(monkeypatch, MOCK_AUTH="").auth_mock_mode is False
    assert _settings(monkeypatch, AUTH_MOCK_MODE="true", APP_ENV="development").auth_mock_mode is True
    assert _settings(monkeypatch, AUTH_MOCK_MODE="true", APP_ENV="staging").auth_mock_mode is False
    assert _settings(monkeypatch, AUTH_MOCK_MODE="false").auth_mock_mode is False


def test_production_refuses_an_explicit_mock_auth_opt_in(monkeypatch):
    settings = _settings(monkeypatch, MOCK_AUTH="1", APP_ENV="production")
    monkeypatch.setattr("app.core.startup.get_settings", lambda: settings)
    monkeypatch.setattr(settings, "clerk_secret_key", "sk_test_placeholder")
    monkeypatch.setattr(settings, "storage_mock_mode", False)
    monkeypatch.setattr(settings, "r2_account_id", "account")
    monkeypatch.setattr(settings, "r2_access_key_id", "key")
    monkeypatch.setattr(settings, "r2_secret_access_key", "secret")

    try:
        validate_configuration()
    except ConfigurationError as exc:
        assert "MOCK_AUTH" in str(exc)
    else:
        raise AssertionError("production started with mock auth requested")


def _real_storage(monkeypatch, settings: Settings) -> None:
    monkeypatch.setattr("app.core.startup.get_settings", lambda: settings)
    monkeypatch.setattr(settings, "storage_mock_mode", False)
    monkeypatch.setattr(settings, "r2_account_id", "account")
    monkeypatch.setattr(settings, "r2_access_key_id", "key")
    monkeypatch.setattr(settings, "r2_secret_access_key", "secret")


@pytest.mark.parametrize("app_env", ["development", "test", " Development ", "TEST"])
def test_mock_auth_is_allowed_for_development_and_test(monkeypatch, app_env):
    settings = _settings(monkeypatch, MOCK_AUTH="1", APP_ENV=app_env)
    assert settings.auth_mock_mode is True
    _real_storage(monkeypatch, settings)

    warnings = validate_configuration()
    assert settings.auth_mock_mode is True
    assert any("mock" in warning.lower() for warning in warnings)


@pytest.mark.parametrize("app_env", ["prod", "prd", "live", "staging", "", "productión"])
def test_mock_auth_is_refused_for_unknown_or_empty_app_env(monkeypatch, app_env):
    settings = _settings(monkeypatch, MOCK_AUTH="1", APP_ENV=app_env)
    assert settings.auth_mock_mode is False
    _real_storage(monkeypatch, settings)
    monkeypatch.setattr(settings, "clerk_secret_key", "sk_test_placeholder")

    with pytest.raises(ConfigurationError, match="MOCK_AUTH"):
        validate_configuration()


def test_unknown_app_env_is_refused_without_mock_auth(monkeypatch):
    settings = _settings(monkeypatch, APP_ENV="staging")
    assert settings.auth_mock_mode is False
    _real_storage(monkeypatch, settings)
    monkeypatch.setattr(settings, "clerk_secret_key", "sk_test_placeholder")

    with pytest.raises(ConfigurationError, match="APP_ENV"):
        validate_configuration()


def test_staging_does_not_accept_a_mock_user_header(monkeypatch):
    settings = _settings(monkeypatch, MOCK_AUTH="1", APP_ENV="staging")
    assert settings.auth_mock_mode is False
    monkeypatch.setattr("app.core.security.settings", settings)
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"x-mock-user-id", b"mock-user-001")],
            "client": ("127.0.0.1", 123),
            "server": ("test", 80),
        }
    )

    with pytest.raises(HTTPException) as caught:
        asyncio.run(get_current_user(request, None))
    assert caught.value.status_code == 401
