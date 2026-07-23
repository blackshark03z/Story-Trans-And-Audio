"""Explicit schema-15 support for production PREPARE.

Migrations 13-15 remain outside the normal startup migration set.  This module
only exposes a verified runner for explicit activation and schema-15 runtime
verification; normal ``Database.initialize()`` continues to target schema 12.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .migrations import MIGRATIONS, MIGRATION_PATTERN, Migration, MigrationRunner, SchemaMigrationError


PREPARE_SCHEMA_VERSION = 15
PREPARE_MIGRATION_HASHES = {
    13: "6021e82a08627f897f3c02ae6f316da78ca8ba55fbc5cb153faf6999637282ba",
    14: "ad6108f18c1b4a113ddd68b3d067a8884ff9e5f1c6df5d8c729b0e31ad5486aa",
    15: "6b5b00e8b013c7876c4faef4c480c0926c3ee8df8304a1c3b3544d80e9fdd706",
}
_DORMANT_ROOT = Path(__file__).resolve().parent / "migrations" / "dormant"


def prepare_migrations() -> list[Migration]:
    migrations = list(MIGRATIONS)
    for version in range(13, PREPARE_SCHEMA_VERSION + 1):
        matches = sorted(_DORMANT_ROOT.glob(f"{version:04d}_*.sql"))
        if len(matches) != 1:
            raise SchemaMigrationError(
                f"Expected exactly one dormant migration for schema {version}; found {len(matches)}."
            )
        path = matches[0]
        match = MIGRATION_PATTERN.match(path.name)
        if not match:
            raise SchemaMigrationError(f"Invalid PREPARE migration filename: {path.name}.")
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        expected = PREPARE_MIGRATION_HASHES[version]
        if checksum != expected:
            raise SchemaMigrationError(
                f"PREPARE migration {version} checksum mismatch; activation is blocked."
            )
        migrations.append(
            Migration(
                version=version,
                name=match.group(2),
                path=path,
                checksum=checksum,
                sql=sql,
            )
        )
    versions = [migration.version for migration in migrations]
    if versions != list(range(1, PREPARE_SCHEMA_VERSION + 1)):
        raise SchemaMigrationError(f"PREPARE migration chain is not contiguous: {versions}.")
    return migrations


def prepare_migration_runner() -> MigrationRunner:
    return MigrationRunner(prepare_migrations())


def verified_prepare_migration_hashes() -> dict[int, str]:
    migrations = prepare_migrations()
    return {
        migration.version: migration.checksum
        for migration in migrations
        if migration.version >= 13
    }


__all__ = [
    "PREPARE_MIGRATION_HASHES",
    "PREPARE_SCHEMA_VERSION",
    "prepare_migration_runner",
    "prepare_migrations",
    "verified_prepare_migration_hashes",
]
