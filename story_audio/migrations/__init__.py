from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


MIGRATION_PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
MIGRATIONS_DIR = Path(__file__).resolve().parent


class SchemaMigrationError(RuntimeError):
    """Base error for schema migration failures."""


class FutureSchemaVersionError(SchemaMigrationError):
    """Raised when a database was created by newer application code."""


class MigrationChecksumError(SchemaMigrationError):
    """Raised when an already-applied migration file was modified."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    sql: str


def discover_migrations() -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        match = MIGRATION_PATTERN.match(path.name)
        if not match:
            continue
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=int(match.group(1)),
                name=match.group(2),
                path=path,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
            )
        )
    versions = [migration.version for migration in migrations]
    if not migrations or versions != list(range(1, len(migrations) + 1)):
        raise SchemaMigrationError(
            f"Migration versions must be contiguous from 1; found {versions}."
        )
    return migrations


MIGRATIONS = discover_migrations()
LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version


def _execute_script_transactionally(connection: sqlite3.Connection, sql: str) -> None:
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if not sqlite3.complete_statement(buffer):
            continue
        statement = buffer.strip()
        buffer = ""
        if statement:
            connection.execute(statement)
    if buffer.strip():
        raise SchemaMigrationError("Migration contains an incomplete SQL statement.")


class MigrationRunner:
    def __init__(self, migrations: list[Migration] | None = None):
        self.migrations = migrations or MIGRATIONS
        self.latest_version = self.migrations[-1].version

    @staticmethod
    def bootstrap(connection: sqlite3.Connection) -> None:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )"""
        )

    def verify_applied(self, connection: sqlite3.Connection) -> int:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not table:
            return 0
        applied_rows = connection.execute(
            "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        applied = {int(row["version"]): row for row in applied_rows}
        current = max(applied, default=0)
        if current > self.latest_version:
            raise FutureSchemaVersionError(
                f"Database schema version {current} is newer than supported version "
                f"{self.latest_version}. Refusing to start."
            )
        known = {migration.version: migration for migration in self.migrations}
        for version, row in applied.items():
            migration = known.get(version)
            if migration is None:
                raise FutureSchemaVersionError(
                    f"Database contains unknown migration version {version}."
                )
            if row["name"] != migration.name or row["checksum"] != migration.checksum:
                raise MigrationChecksumError(
                    f"Migration {version:04d}_{migration.name} checksum/name mismatch."
                )
        return current

    def current_version(self, connection: sqlite3.Connection) -> int:
        return self.verify_applied(connection)

    def apply(self, connection: sqlite3.Connection, applied_at: str) -> int:
        self.bootstrap(connection)
        connection.commit()
        self.verify_applied(connection)
        applied_rows = connection.execute(
            "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        applied = {int(row["version"]): row for row in applied_rows}

        for migration in self.migrations:
            if migration.version in applied:
                continue
            connection.execute("BEGIN IMMEDIATE")
            try:
                _execute_script_transactionally(connection, migration.sql)
                connection.execute(
                    "INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)",
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        applied_at,
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return self.latest_version


__all__ = [
    "FutureSchemaVersionError",
    "LATEST_SCHEMA_VERSION",
    "MigrationChecksumError",
    "MigrationRunner",
    "SchemaMigrationError",
]
