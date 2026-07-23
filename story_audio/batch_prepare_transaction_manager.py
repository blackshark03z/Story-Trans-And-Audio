from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .config import canonical_production_db_path


class IsolatedTransactionError(RuntimeError):
    """Base error for the dormant Phase 9 transaction boundary."""


class CanonicalDatabaseRejected(IsolatedTransactionError):
    pass


class IsolatedTransactionBusy(IsolatedTransactionError):
    pass


class IsolatedTransactionStateError(IsolatedTransactionError):
    pass


def _resolved_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.expanduser().resolve(strict=False))))


def assert_isolated_database_path(path: Path, *, allow_canonical: bool = False) -> Path:
    requested = path.expanduser().resolve(strict=False)
    canonical = canonical_production_db_path().resolve(strict=False)
    same = _resolved_key(requested) == _resolved_key(canonical)
    if not same and requested.exists() and canonical.exists():
        try:
            same = os.path.samefile(requested, canonical)
        except OSError:
            same = False
    if same and not allow_canonical:
        raise CanonicalDatabaseRejected("Phase 9 isolated transaction infrastructure rejects the canonical database")
    return requested


class IsolatedWriteTransaction:
    def __init__(self, connection: sqlite3.Connection, transaction_reference: str):
        self.connection = connection
        self.transaction_reference = transaction_reference
        self.connection_identity = id(connection)
        self._state = "active"

    @property
    def active(self) -> bool:
        return self._state == "active" and self.connection.in_transaction

    def require_active(self) -> sqlite3.Connection:
        if not self.active:
            raise IsolatedTransactionStateError("caller-owned transaction is not active")
        return self.connection

    def commit(self) -> None:
        self.require_active()
        try:
            self.connection.commit()
        except Exception:
            self._state = "outcome_unknown"
            raise
        else:
            self._state = "committed"

    def rollback(self) -> None:
        if self._state != "active":
            raise IsolatedTransactionStateError("transaction can only roll back while active")
        try:
            self.connection.rollback()
        finally:
            self._state = "rolled_back"

    def close(self) -> None:
        if self._state == "active":
            self.connection.rollback()
            self._state = "rolled_back"
        self.connection.close()


class BatchPrepareTransactionManager:
    """One-shot BEGIN IMMEDIATE manager for disposable Phase 9 databases."""

    def __init__(
        self,
        db_path: Path,
        *,
        busy_timeout_ms: int = 5000,
        allow_canonical: bool = False,
    ):
        self.db_path = assert_isolated_database_path(
            Path(db_path),
            allow_canonical=allow_canonical,
        )
        if not 1 <= int(busy_timeout_ms) <= 30000:
            raise ValueError("busy_timeout_ms must be between 1 and 30000")
        self.busy_timeout_ms = int(busy_timeout_ms)

    def begin(self, transaction_reference: str) -> IsolatedWriteTransaction:
        reference = str(transaction_reference or "").strip()
        if not 1 <= len(reference) <= 200:
            raise ValueError("transaction_reference must contain 1-200 characters")
        connection = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout_ms / 1000,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            connection.close()
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise IsolatedTransactionBusy("isolated PREPARE writer reservation timed out") from exc
            raise IsolatedTransactionError("isolated PREPARE transaction could not begin") from exc
        return IsolatedWriteTransaction(connection, reference)


__all__ = [
    "BatchPrepareTransactionManager",
    "CanonicalDatabaseRejected",
    "IsolatedTransactionBusy",
    "IsolatedTransactionError",
    "IsolatedTransactionStateError",
    "IsolatedWriteTransaction",
    "assert_isolated_database_path",
]
