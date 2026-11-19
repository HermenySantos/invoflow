"""The receipt screen shows a PATCH /documents/{id} detail only when it is on its PT-PT allowlist."""

from pathlib import Path

import pytest

from app.api.documents import EDIT_BUSY_DETAIL
from app.core.db_errors import DB_BUSY_DETAIL, DB_INTERRUPTED_DETAIL
from app.schemas.document import (
    AMOUNT_MISMATCH_DETAIL,
    NULL_TYPE_DETAIL,
    SERIES_MISMATCH_DETAIL,
    TYPE_REQUIRED_DETAIL,
)

REPO = Path(__file__).resolve().parents[2]
FRONTEND_LIB = REPO / "frontend" / "lib"
DOCUMENTS_API = REPO / "backend" / "app" / "api" / "documents.py"

DUPLICATE_WITHOUT_NUMBER = "Já existe outro documento com este NIF e n.º."
DUPLICATE_WITH_NUMBER_PREFIX = 'f"Já existe outro documento com o n.º {number}."'


def _frontend_allowlist() -> str:
    return (FRONTEND_LIB / "saveError.ts").read_text(encoding="utf-8") + (
        FRONTEND_LIB / "reviewEdit.ts"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "detail",
    [
        EDIT_BUSY_DETAIL,
        DB_BUSY_DETAIL,
        DB_INTERRUPTED_DETAIL,
        AMOUNT_MISMATCH_DETAIL,
        NULL_TYPE_DETAIL,
        SERIES_MISMATCH_DETAIL,
        TYPE_REQUIRED_DETAIL,
        DUPLICATE_WITHOUT_NUMBER,
    ],
)
def test_frontend_allowlist_has_every_save_detail(detail):
    assert detail in _frontend_allowlist()


def test_rate_limited_detail_carries_the_wait_the_frontend_reads():
    import re

    from app.core.rate_limit import RATE_LIMITED_MESSAGE

    frontend = (FRONTEND_LIB / "rateLimit.ts").read_text(encoding="utf-8")
    assert "/Aguarde (\\d+) s/" in frontend
    assert re.search(r"Aguarde (\d+) s", RATE_LIMITED_MESSAGE.format(seconds=42)).group(1) == "42"


def test_duplicate_details_are_the_ones_the_frontend_matches():
    source = DOCUMENTS_API.read_text(encoding="utf-8")
    assert f'"{DUPLICATE_WITHOUT_NUMBER}"' in source
    assert DUPLICATE_WITH_NUMBER_PREFIX in source
    assert "Já existe outro documento com o n\\.º" in (FRONTEND_LIB / "saveError.ts").read_text(encoding="utf-8")
