"""The sample env file must load. DEBUG is not a setting and is rejected."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def test_env_example_loads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=EXAMPLE)
    assert settings.app_env == "development"
    assert settings.auth_mock_mode is True


def test_debug_env_name_is_rejected(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEBUG=true\n", encoding="utf-8")
    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=env_file)
    assert any(error["type"] == "extra_forbidden" for error in raised.value.errors())
