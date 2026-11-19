"""Production refuses to start on SQLite, with unsafe CORS origins, or with APP_DEBUG on."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.core.startup import ConfigurationError, validate_configuration

BACKEND = Path(__file__).resolve().parents[1]
SECRET = "s3cret-do-not-print"

VALID_PRODUCTION = {
    "APP_ENV": "production",
    "DATABASE_URL": f"postgresql://invoflow:{SECRET}@db.invalid:5432/invoflow",
    "CLERK_SECRET_KEY": "sk_live_placeholder",
    "CLERK_FRONTEND_API": "clerk.invoflow.example.pt",
    "CLERK_AUTHORIZED_PARTIES": "https://invoflow.example.pt",
    "CORS_ORIGINS": "https://invoflow.example.pt",
    "STORAGE_MOCK_MODE": "false",
    "R2_ACCOUNT_ID": "placeholder",
    "R2_ACCESS_KEY_ID": "placeholder",
    "R2_SECRET_ACCESS_KEY": "placeholder",
    "R2_BUCKET_NAME": "invoflow-documents",
    "OCR_BACKEND": "azure",
    "AZURE_DOC_ENDPOINT": "https://placeholder.cognitiveservices.azure.com/",
    "AZURE_DOC_KEY": "placeholder",
}

# (overrides, setting named in the error, value that must not be printed)
REFUSED = {
    "debug_on": ({"APP_DEBUG": "true"}, "APP_DEBUG", None),
    "sqlite_by_default": ({"DATABASE_URL": None}, "DATABASE_URL points at SQLite", None),
    "sqlite_explicit": ({"DATABASE_URL": f"sqlite:////data/{SECRET}.db"}, "DATABASE_URL points at SQLite", SECRET),
    "not_postgres": ({"DATABASE_URL": f"mysql://invoflow:{SECRET}@db/invoflow"}, "DATABASE_URL", SECRET),
    "cors_localhost": ({"CORS_ORIGINS": "https://localhost:3000"}, "CORS_ORIGINS entry 1", "localhost"),
    "cors_loopback_ip": ({"CORS_ORIGINS": "https://127.0.0.1"}, "CORS_ORIGINS entry 1", "127.0.0.1"),
    "cors_http": ({"CORS_ORIGINS": f"http://{SECRET}.example"}, "CORS_ORIGINS entry 1", SECRET),
    "cors_wildcard": ({"CORS_ORIGINS": "*"}, "CORS_ORIGINS entry 1", None),
    "cors_empty": ({"CORS_ORIGINS": "[]"}, "CORS_ORIGINS must list", None),
    "cors_second_entry_local": (
        {"CORS_ORIGINS": "https://invoflow.example.pt,http://localhost:3000"},
        "CORS_ORIGINS entry 2",
        "localhost:3000",
    ),
}


def _env(overrides: dict) -> dict:
    env = {**VALID_PRODUCTION, **overrides}
    return {name: value for name, value in env.items() if value is not None}


def _validate(monkeypatch, env: dict) -> list:
    fields = {field.upper() for field in Settings.model_fields}
    for name in list(os.environ):
        if name.upper() in fields:
            monkeypatch.delenv(name)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)
    monkeypatch.setattr("app.core.startup.get_settings", lambda: settings)
    return validate_configuration()


def test_valid_production_config_starts(monkeypatch):
    _validate(monkeypatch, _env({}))


def test_valid_production_config_with_several_origins_starts(monkeypatch):
    _validate(monkeypatch, _env({"CORS_ORIGINS": '["https://invoflow.example.pt","https://www.invoflow.example.pt"]'}))


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_production_refuses_to_start(monkeypatch, case):
    overrides, named, hidden = REFUSED[case]
    with pytest.raises(ConfigurationError) as raised:
        _validate(monkeypatch, _env(overrides))
    message = str(raised.value)
    assert named in message
    assert SECRET not in message
    if hidden:
        assert hidden not in message


def test_development_keeps_the_demo_defaults(monkeypatch):
    warnings = _validate(monkeypatch, {"APP_ENV": "development", "MOCK_AUTH": "1", "OCR_BACKEND": "mock"})
    assert any("SQLite" in warning for warning in warnings)


def test_test_env_keeps_sqlite_localhost_and_mock_auth(monkeypatch):
    _validate(
        monkeypatch,
        {
            "APP_ENV": "test",
            "MOCK_AUTH": "1",
            "OCR_BACKEND": "mock",
            "DATABASE_URL": "sqlite:///:memory:",
            "CORS_ORIGINS": "http://localhost:3000",
            "STORAGE_MOCK_MODE": "false",
            "R2_ACCOUNT_ID": "a",
            "R2_ACCESS_KEY_ID": "b",
            "R2_SECRET_ACCESS_KEY": "c",
        },
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _uvicorn(env: dict, cwd: Path, port: int) -> subprocess.Popen:
    # A clean environment and an empty cwd, so neither the test settings nor a local .env leak in.
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(BACKEND), "--port", str(port)],
        cwd=cwd,
        env={"PATH": os.environ.get("PATH", ""), "HOME": str(cwd), **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


@pytest.mark.parametrize("case", ["sqlite_explicit", "cors_localhost", "cors_http"])
def test_uvicorn_exits_non_zero_without_printing_values(tmp_path, case):
    overrides, named, hidden = REFUSED[case]
    process = _uvicorn(_env(overrides), tmp_path, _free_port())
    output, _ = process.communicate(timeout=120)
    assert process.returncode != 0, output
    assert "Application startup failed" in output
    assert named in output
    assert SECRET not in output
    if hidden:
        assert hidden not in output


@pytest.mark.skipif(
    not os.environ.get("PRODUCTION_START_DATABASE_URL"),
    reason="needs a migrated Postgres in PRODUCTION_START_DATABASE_URL (CI migrations job)",
)
def test_uvicorn_serves_with_valid_production_config(tmp_path):
    port = _free_port()
    process = _uvicorn(_env({"DATABASE_URL": os.environ["PRODUCTION_START_DATABASE_URL"]}), tmp_path, port)
    try:
        deadline = time.monotonic() + 60
        while True:
            assert process.poll() is None, process.communicate()[0]
            try:
                health = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
                break
            except httpx.TransportError:
                assert time.monotonic() < deadline, "API did not come up"
                time.sleep(0.5)
        assert health.status_code == 200, health.text
    finally:
        process.terminate()
        process.wait(timeout=30)
