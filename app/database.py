import hashlib
import os
from pathlib import Path

import aiosqlite

DB_PATH = os.getenv("DB_PATH", "/data/cairn.db")
MIGRATIONS_PATH = Path(__file__).parent.parent / "migrations"


async def run_migrations():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version    INTEGER PRIMARY KEY,
                checksum   TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.commit()

        result = await db.execute("SELECT version, checksum FROM schema_version")
        applied = {row[0]: row[1] for row in await result.fetchall()}

        migration_files = sorted(MIGRATIONS_PATH.glob("*.sql"))

        for migration_file in migration_files:
            version = int(migration_file.stem.split("_")[0])
            sql = migration_file.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()

            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError(
                        f"Migration {migration_file.name} has been modified after being applied. "
                        f"Expected checksum {applied[version]}, got {checksum}."
                    )
                continue

            print(f"Applying migration {migration_file.name}")
            await db.executescript(sql)
            await db.execute(
                "INSERT INTO schema_version (version, checksum) VALUES (?, ?)",
                (version, checksum),
            )
            await db.commit()


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db
