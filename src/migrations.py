"""Ordered, transactional SQL migrations; run with python -m src.migrations."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from src.tracker import get_conn

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
# All runners must use the same transaction-scoped advisory lock.
MIGRATION_LOCK = 724810291


def migration_files(directory: Path) -> list[tuple[int, Path, str]]:
    files = []
    for path in directory.glob("*.sql"):
        match = re.fullmatch(r"(\d{3,})_[a-z0-9_]+\.sql", path.name)
        if not match:
            raise ValueError(f"Invalid migration filename: {path.name}")
        files.append((int(match[1]), path, hashlib.sha256(path.read_bytes()).hexdigest()))
    files.sort(key=lambda item: item[0])
    if not files or [item[0] for item in files] != list(range(1, len(files) + 1)):
        raise ValueError("Migrations must have unique, contiguous versions starting at 001")
    return files


def apply_migrations(conn, directory: Path = MIGRATIONS) -> list[str]:
    """Apply pending files inside the caller's transaction (never commit here).

    The first run replays the existing idempotent 001/002 SQL to adopt legacy
    installations. Subsequent runs refuse edited, renamed, or missing history.
    A failed batch rolls back schema changes and ledger entries together.
    """
    files = migration_files(directory)
    applied = []
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("SELECT version, filename, sha256 FROM schema_migrations ORDER BY version")
        history = cur.fetchall()
        expected = [(v, p.name, digest) for v, p, digest in files]
        actual = [(row["version"], row["filename"], row["sha256"]) for row in history]
        if actual != expected[:len(actual)]:
            raise ValueError("Migration history differs from disk; restore applied files")
        for version, path, digest in files[len(actual):]:
            cur.execute(path.read_text(encoding="utf-8"))
            cur.execute(
                "INSERT INTO schema_migrations (version, filename, sha256) VALUES (%s, %s, %s)",
                (version, path.name, digest),
            )
            applied.append(path.name)
    return applied


def migrate() -> list[str]:
    with get_conn() as conn:
        return apply_migrations(conn)


if __name__ == "__main__":
    print("Applied: " + (", ".join(migrate()) or "none (up to date)"))
