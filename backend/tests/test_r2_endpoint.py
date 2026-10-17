from pathlib import Path

from app.services.storage import resolve_r2_endpoint

ROOT = Path(__file__).resolve().parents[2]
EU_HOST = ".eu.r2.cloudflarestorage.com"


def test_unset_endpoint_uses_the_eu_jurisdiction_host():
    assert resolve_r2_endpoint("acct", "") == f"https://acct{EU_HOST}"
    assert resolve_r2_endpoint("acct", "  ") == f"https://acct{EU_HOST}"


def test_an_explicit_endpoint_wins():
    assert resolve_r2_endpoint("acct", "http://s3:9090") == "http://s3:9090"


def test_deploy_docs_and_backup_scripts_name_the_eu_host():
    readme = (ROOT / "deploy/README.md").read_text(encoding="utf-8")
    example = (ROOT / "deploy/.env.example").read_text(encoding="utf-8")
    backup = (ROOT / "deploy/backup/backup.sh").read_text(encoding="utf-8")
    restore = (ROOT / "deploy/backup/restore.sh").read_text(encoding="utf-8")
    for text in (readme, example, backup, restore):
        assert EU_HOST in text
