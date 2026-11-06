"""Postgres failures the user can simply retry, and their PT-PT copy.

The transaction is always rolled back first, so nothing was saved.
"""

from typing import Optional

from fastapi import HTTPException, status

DB_BUSY_CODE = "DATABASE_BUSY"
DB_INTERRUPTED_CODE = "DATABASE_INTERRUPTED"
DB_BUSY_DETAIL = (
    "Outra operação nesta conta estava a decorrer ao mesmo tempo. "
    "Nada foi guardado; tente novamente dentro de momentos."
)
DB_INTERRUPTED_DETAIL = (
    "A operação demorou demasiado e foi interrompida. Nada foi guardado; tente novamente."
)
RETRY_AFTER_SECONDS = "5"

# Deadlock, serialization failure, lock wait timed out.
_CONFLICT_STATES = frozenset({"40P01", "40001", "55P03"})
# Statement timeout, idle-in-transaction timeout.
_INTERRUPTED_STATES = frozenset({"57014", "25P03"})


def sqlstate(exc: BaseException) -> Optional[str]:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)


def is_lock_conflict(exc: BaseException) -> bool:
    return sqlstate(exc) in _CONFLICT_STATES


def is_interrupted(exc: BaseException) -> bool:
    """A statement or idle limit ended the transaction.

    When the server ends an idle session, psycopg2 reports only a closed
    connection, without SQLSTATE 25P03, so a dropped connection counts too.
    """
    return sqlstate(exc) in _INTERRUPTED_STATES or bool(getattr(exc, "connection_invalidated", False))


def retryable(exc: BaseException) -> Optional[tuple[str, str]]:
    """(code, PT-PT detail) when the user can retry, else None."""
    if is_lock_conflict(exc):
        return DB_BUSY_CODE, DB_BUSY_DETAIL
    if is_interrupted(exc):
        return DB_INTERRUPTED_CODE, DB_INTERRUPTED_DETAIL
    return None


def retryable_http_error(exc: BaseException) -> Optional[HTTPException]:
    found = retryable(exc)
    if found is None:
        return None
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=found[1],
        headers={"Retry-After": RETRY_AFTER_SECONDS},
    )
