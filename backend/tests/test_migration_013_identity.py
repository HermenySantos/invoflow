"""Migration 013's frozen identity matches the app normaliser."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.services.efatura import at_invoice_identity


_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/013_recompute_identity.py"
)

# Inputs the normaliser treats differently from a plain casefold.
_CORPUS = (
    ("296123456", "NC", "NC. 2026/5"),
    ("296123456", "NC", "NC..2026/5"),
    ("296123456", "NC", "NC;2026/5"),
    ("296123456", "NC", "NC'2026/5"),
    ("296123456", "NC", "NC*2026/5"),
    ("296123456", "NC", "NC+2026/5"),
    ("296123456", "NC", "NC/2026/5"),
    ("296123456", "NC", "NC(2026)5"),
    ("296123456", "NC", "nc - 2026 / 005"),
    ("296123456", "NC", "NC\u00ba2026/5"),
    ("296123456", "NC", "NC\u00b02026/5"),
    ("296123456", "NC", "NC\u00ba1"),
    ("296123456", "FT", "FT\u00b02026/5"),
    ("123456002", "FT", "FT2026/12"),
    ("123456002", "NC", "NC2026/005"),
    ("123456002", "ND", "ND5"),
    ("296123456", "FT", "FTA 2026/5"),
    ("296123456", "FT", "FT A 2026/5"),
    ("296123456", "NC", "NCB/12"),
    ("296123456", "NC", "NC B/12"),
    ("296123456", "FT", "FT;A 1/5"),
    ("296123456", "FS", "FS_1"),
    ("296123456", "FT", "FT A01/5"),
    ("296123456", "FT", "FT A1/5"),
    ("296123456", "FT", "FT A1/005"),
    ("296123456", "FT", "FT A01/005"),
    ("296123456", "NC", "NC;007/001"),
    ("296123456", "FT", "FT 007/1"),
    ("296123456", "FT", "FT 7/1"),
    ("296123456", "FT", "FT 1 23/4"),
    ("296123456", "FT", "FT  1   23/4"),
    ("296123456", "FT", "FT 12 3/4"),
    ("296123456", "FT", "FT 1 23 / 4"),
    ("500100144", "FT", "FT\u00a02026/12"),
    ("500100144", "FT", "FT\u202f2026/012"),
    ("500100144", "FT", "FT\u20072026/12"),
    ("500100144", "FT", "FT\u20092026/12"),
    ("500100144", "ft", "FT  2026/012"),
    ("PT 500100144", "FT", "FT A/1"),
    ("PT500100144", "FT", "FT A/1"),
    ("PT296123456", "FT", "FT A/1"),
    ("PTX1", "FT", "FT A/1"),
    ("pt 123456789", "NC", "NC 1/1"),
    ("123 456 002", "FT", "FT 1/1"),
    ("PT 500100144", "FT", "FT\u00a02026/12"),
    (None, None, None),
    (None, "FT", None),
    ("PT 500100144", None, None),
    ("", "", ""),
    ("PT", "FT", "FT A/1"),
    ("296123456", "  ft  ", "FS_1"),
    ("296123456", "nc", None),
)


def _frozen():
    spec = importlib.util.spec_from_file_location(
        "migration_013_recompute_identity",
        _MIGRATION,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.at_invoice_identity


@pytest.fixture(scope="module")
def frozen_identity():
    return _frozen()


def test_migration_013_does_not_import_the_app():
    source = _MIGRATION.read_text()
    assert "import app" not in source
    assert "from app." not in source


def _series_folded(identity: str) -> str:
    nif, kind, number = identity.split("|", 2)
    return f"{nif}|{kind}|{number.casefold()}"


@pytest.mark.parametrize(("nif", "kind", "number"), _CORPUS)
def test_migration_013_identity_matches_the_app_up_to_series_case(
    frozen_identity, nif, kind, number
):
    # 013 casefolded the series. Migration 014 recomputes with the series' case kept.
    assert frozen_identity.__module__ != at_invoice_identity.__module__
    assert frozen_identity(nif, kind, number) == _series_folded(at_invoice_identity(nif, kind, number))
