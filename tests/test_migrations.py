from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from uuid import uuid4

import psycopg2
import pytest

from src.migrations import apply_migrations, migration_files
from src.tracker import get_conn


def test_invalid_order_rejected(tmp_path):
    (tmp_path / "002_late.sql").write_text("SELECT 1")
    with pytest.raises(ValueError, match="contiguous"):
        migration_files(tmp_path)
    (tmp_path / "001_first.sql").write_text("SELECT 1")
    (tmp_path / "001_duplicate.sql").write_text("SELECT 1")
    with pytest.raises(ValueError, match="unique"):
        migration_files(tmp_path)


@pytest.fixture
def isolated_schema():
    if not os.getenv("POSTGRES_URL"):
        pytest.skip("POSTGRES_URL required")
    schema = "migration_test_" + uuid4().hex
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
    yield schema
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA "{schema}" CASCADE')


def run_in_schema(schema, directory):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SET LOCAL search_path TO "{schema}"')
        return apply_migrations(conn, directory)


def test_apply_repeat_and_history_integrity(isolated_schema, tmp_path):
    first = tmp_path / "001_first.sql"
    first.write_text("CREATE TABLE sample (id INTEGER)")
    assert run_in_schema(isolated_schema, tmp_path) == [first.name]
    assert run_in_schema(isolated_schema, tmp_path) == []
    second = tmp_path / "002_second.sql"
    second.write_text("ALTER TABLE sample ADD COLUMN label TEXT")
    assert run_in_schema(isolated_schema, tmp_path) == [second.name]
    first.write_text("CREATE TABLE sample (id BIGINT)")
    with pytest.raises(ValueError, match="history"):
        run_in_schema(isolated_schema, tmp_path)
    first.write_text("CREATE TABLE sample (id INTEGER)")
    second.unlink()
    with pytest.raises(ValueError, match="history"):
        run_in_schema(isolated_schema, tmp_path)


def test_failure_rolls_back_ddl_and_ledger(isolated_schema, tmp_path):
    (tmp_path / "001_first.sql").write_text("CREATE TABLE sample (id INTEGER)")
    second = tmp_path / "002_bad.sql"
    second.write_text("SELECT * FROM missing_table")
    with pytest.raises(psycopg2.errors.UndefinedTable):
        run_in_schema(isolated_schema, tmp_path)
    second.write_text("INSERT INTO sample VALUES (1)")
    assert len(run_in_schema(isolated_schema, tmp_path)) == 2


def test_concurrent_runners_apply_once(isolated_schema, tmp_path):
    (tmp_path / "001_first.sql").write_text("CREATE TABLE sample (id INTEGER)")
    barrier = Barrier(2)

    def run():
        barrier.wait(timeout=10)
        return run_in_schema(isolated_schema, tmp_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(map(len, results)) == [0, 1]


def test_actual_legacy_upgrade_preserves_job_and_adds_delivery_ledger():
    from src.migrations import MIGRATIONS
    from psycopg2.extensions import make_dsn
    from psycopg2.extras import RealDictCursor
    from psycopg2.sql import SQL, Identifier
    if not os.getenv("POSTGRES_URL"):
        pytest.skip("POSTGRES_URL required")
    # Historical foundation SQL assumes one public application schema per DB.
    database = "migration_rehearsal_" + uuid4().hex
    admin = psycopg2.connect(os.environ["POSTGRES_URL"])
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(SQL("CREATE DATABASE {}").format(Identifier(database)))
        conn = psycopg2.connect(make_dsn(os.environ["POSTGRES_URL"], dbname=database), cursor_factory=RealDictCursor)
        try:
            with conn, conn.cursor() as cur:
                cur.execute((MIGRATIONS / "001_jobs.sql").read_text())
                cur.execute("INSERT INTO jobs (title, company, url, source) VALUES ('Legacy Engineer', 'Example', 'https://example.com/legacy', 'test')")
                assert len(apply_migrations(conn)) == 3
                cur.execute("SELECT title FROM jobs WHERE url = 'https://example.com/legacy'")
                assert cur.fetchone()["title"] == "Legacy Engineer"
                cur.execute("SELECT count(*) AS n FROM delivery_attempts")
                assert cur.fetchone()["n"] == 0
                assert apply_migrations(conn) == []
        finally:
            conn.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(SQL("DROP DATABASE IF EXISTS {}").format(Identifier(database)))
        admin.close()
