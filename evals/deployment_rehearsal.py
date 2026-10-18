"""Rehearse migrations, backup/restore and protected HTTP reads on disposable local DBs.

Creates two uniquely named databases and retains them for inspection. Never starts
workers, fetches jobs, calls a model or sends mail. Requires local PostgreSQL tools.
"""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg2
from psycopg2 import sql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-local', action='store_true', required=True)
    parser.add_argument('--port', type=int, default=55439)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new output path')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as out:
        out.write('{}\n')
    args.output.chmod(0o600)
    tag = uuid4().hex[:12]
    primary, restored = f'rehearsal_{tag}', f'restore_{tag}'
    report = dict(passed=False, scope='Local disposable databases only',
                  primary=primary, restored=restored, scheduler_started=False)
    env = {**os.environ, 'PYTHON_DOTENV_DISABLED': '1',
           'PGHOST': '127.0.0.1', 'PGPORT': str(args.port), 'PGUSER': 'postgres'}
    env.pop('PGPASSWORD', None)
    worker = None
    dump = args.output.with_suffix('.dump')
    def connect(database):
        return psycopg2.connect(host='127.0.0.1', port=args.port, user='postgres', dbname=database)
    try:
        admin = connect('postgres')
        admin.autocommit = True
        try:
            with admin.cursor() as cur:
                for name in (primary, restored):
                    cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        finally:
            admin.close()
        env['POSTGRES_URL'] = f'postgresql://postgres@127.0.0.1:{args.port}/{primary}'
        for _ in range(2):
            subprocess.run([sys.executable, '-m', 'src.migrations'], env=env, check=True,
                           capture_output=True, timeout=60)
        with connect(primary) as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO jobs (title, company, location, url, source, description) VALUES (%s,%s,%s,%s,%s,%s)",
                        ('Rehearsal Engineer', 'Fictional Company', 'Toronto',
                         'https://example.com/rehearsal', 'fixture', 'Synthetic backup sentinel'))
        subprocess.run(['pg_dump', '-Fc', '-f', str(dump), primary], env=env,
                       check=True, capture_output=True, timeout=60)
        dump.chmod(0o600)
        subprocess.run(['pg_restore', '--exit-on-error', '-d', restored, str(dump)], env=env,
                       check=True, capture_output=True, timeout=60)
        env['POSTGRES_URL'] = f'postgresql://postgres@127.0.0.1:{args.port}/{restored}'
        for _ in range(2):
            subprocess.run([sys.executable, '-m', 'src.migrations'], env=env,
                           check=True, capture_output=True, timeout=60)
        def snapshot(name):
            with connect(name) as conn, conn.cursor() as cur:
                cur.execute('SELECT * FROM schema_migrations ORDER BY version')
                migrations = cur.fetchall()
                cur.execute('SELECT id, title, description FROM jobs ORDER BY id')
                return migrations, cur.fetchall()
        report['backup_restore_equal'] = snapshot(primary) == snapshot(restored)
        report['retained_jobs'] = len(snapshot(restored)[1])
        token = secrets.token_urlsafe(32)
        env.update(API_TOKEN=token, API_REQUIRE_READ_AUTH='true', AGENT_WORKFLOW_ENABLED='false')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        worker = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'src.api:app',
                                   '--host', '127.0.0.1', '--port', str(port)], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f'http://127.0.0.1:{port}'
        for _ in range(100):
            try:
                httpx.get(base + '/jobs', timeout=1)
                break
            except httpx.TransportError:
                time.sleep(.1)
        statuses = {}
        for path in ('/jobs', '/pipeline/runs', '/sources/health', '/deliveries'):
            denied = httpx.get(base + path, timeout=5)
            allowed = httpx.get(base + path, headers={'Authorization': f'Bearer {token}'}, timeout=5)
            statuses[path] = dict(unauthenticated=denied.status_code, authenticated=allowed.status_code)
        report['http_reads'] = statuses
        report['passed'] = report['backup_restore_equal'] and report['retained_jobs'] == 1 and all(
            r == dict(unauthenticated=401, authenticated=200) for r in statuses.values())
    except Exception as exc:
        report['error_type'] = type(exc).__name__
    finally:
        if worker is not None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
        args.output.write_text(json.dumps(report, indent=2, default=str) + '\n')
        print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
