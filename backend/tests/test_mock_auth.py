from app.core.config import Settings
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
    assert _settings(monkeypatch, MOCK_AUTH="yes", APP_ENV="staging").auth_mock_mode is True
    assert _settings(monkeypatch, MOCK_AUTH="0").auth_mock_mode is False
    assert _settings(monkeypatch, MOCK_AUTH="").auth_mock_mode is False
    assert _settings(monkeypatch, AUTH_MOCK_MODE="true").auth_mock_mode is True
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


def test_explicit_mock_auth_is_allowed_outside_production(monkeypatch):
    settings = _settings(monkeypatch, MOCK_AUTH="1", APP_ENV="staging")
    monkeypatch.setattr("app.core.startup.get_settings", lambda: settings)
    monkeypatch.setattr(settings, "storage_mock_mode", False)
    monkeypatch.setattr(settings, "r2_account_id", "account")
    monkeypatch.setattr(settings, "r2_access_key_id", "key")
    monkeypatch.setattr(settings, "r2_secret_access_key", "secret")

    warnings = validate_configuration()
    assert settings.auth_mock_mode is True
    assert any("bypassed" in warning.lower() or "mock" in warning.lower() for warning in warnings)
