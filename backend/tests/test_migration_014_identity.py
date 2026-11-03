"""Migration 014's frozen identity matches the app normaliser."""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import pytest

from app.services import efatura
from app.services.efatura import at_invoice_identity
from tests.test_gil160_shared_parse import CORPUS
from tests.test_migration_013_identity import _CORPUS as _013_CORPUS


MIGRATION = Path(__file__).resolve().parents[1] / "alembic/versions/014_series_case_identity.py"

_EXTRA = (
    "FT A/5",
    "FT a/5",
    "ft a/5",
    "FTa/5",
    "FT -A/5",
    "FT .A/5",
    "FT _A/5",
    "FT - A/5",
    "FT-A/5",
    "FRA2026/12",
    "FR A2026/12",
    "FRA 2026/12",
    "FTSL/3",
    "FTS L/3",
    "FT SL/3",
    "FT Straße/1",
    "FT STRASSE/1",
)


def load_migration_014():
    spec = importlib.util.spec_from_file_location("migration_014_series_case_identity", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def frozen():
    return load_migration_014()


def _random_numbers(count: int) -> list[str]:
    rng = random.Random(205)
    pool = "FTSRNCDftsrncdAaBbLlOo0123456789 /-._º°\u00a0\u2013\u200b"
    return ["".join(rng.choice(pool) for _ in range(rng.randint(1, 14))) for _ in range(count)]


def test_migration_014_does_not_import_the_app():
    source = MIGRATION.read_text()
    assert "import app" not in source
    assert "from app." not in source


@pytest.mark.parametrize(("nif", "kind", "number"), _013_CORPUS)
def test_migration_014_identity_matches_the_app(frozen, nif, kind, number):
    assert frozen.at_invoice_identity.__module__ != at_invoice_identity.__module__
    assert frozen.at_invoice_identity(nif, kind, number) == at_invoice_identity(nif, kind, number)


def test_migration_014_identity_and_scan_key_match_the_app_on_corpus_and_random_strings(frozen):
    numbers = [*CORPUS, *_EXTRA, *_random_numbers(20000)]
    for number in numbers:
        assert frozen.at_invoice_identity("296123456", "FT", number) == at_invoice_identity(
            "296123456", "FT", number
        ), number
        assert frozen._scan_number(number) == efatura._scan_number(number), number
