"""Send exactly one synthetic digest through the durable delivery boundary.

Requires explicit recipient/send flag and a fresh local database. Never reads
backlog, scrapes, calls a model or starts scheduling. Retains the DB for audit.
"""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg2
from psycopg2 import sql

from src.settings import get_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--allow-send', action='store_true')
    mode.add_argument('--simulate', action='store_true', help='Fake transport; cannot contact Gmail')
    parser.add_argument('--recipient', required=True)
    parser.add_argument('--port', type=int, default=55439)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or '@' not in args.recipient or any(c in args.recipient for c in '\r\n,;'):
        parser.error('Use a new report path and a single email address')
    os.environ['DIGEST_RECIPIENT'] = args.recipient
    database = 'mailtest_' + uuid4().hex[:12]
    os.environ['POSTGRES_URL'] = f'postgresql://postgres@127.0.0.1:{args.port}/{database}'
    get_settings.cache_clear()
    # Fail before preparing any send if OAuth is missing. Never print credentials.
    if args.allow_send:
        get_settings().require_gmail_credentials()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write('{}\n')
    args.output.chmod(0o600)
    report = dict(passed=False, database=database, status='preparing', recipient=args.recipient, simulated=args.simulate)
    run_id = None
    try:
        admin = psycopg2.connect(host='127.0.0.1', port=args.port, user='postgres', dbname='postgres')
        admin.autocommit = True
        try:
            with admin.cursor() as cur:
                cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        finally:
            admin.close()
        from src.tracker import upsert_job, start_pipeline_run, complete_pipeline_run, fail_pipeline_run, pipeline_execution_lock
        from src.delivery import deliver_digest, list_attempts
        from src.emailer import send_digest
        from src.migrations import migrate
        migrate()
        with pipeline_execution_lock():
            job_id, _ = upsert_job('TEST ONLY — Fictional Software Engineer', 'Synthetic Test Company',
                                  'Toronto', 'https://example.com/job-agent-test',
                                  'Synthetic email acceptance test. This is not a real job.', 'fixture')
            run_id = start_pipeline_run('manual')
            job = dict(id=job_id, title='TEST ONLY — Fictional Software Engineer',
                       company='Synthetic Test Company', location='Toronto', source='fixture',
                       url='https://example.com/job-agent-test', match_score=.9,
                       changes_made='Synthetic test digest; no real application or CV was submitted')
            report['status'] = 'send_attempt_starting'
            args.output.write_text(json.dumps(report, indent=2) + '\n')
            count = deliver_digest([job], run_id=run_id, send=(lambda *a, **kw: True) if args.simulate else send_digest)
            complete_pipeline_run(run_id, jobs_notified=count)
            report.update(passed=count == 1, status='simulated' if args.simulate else 'transport_acknowledged',
                          inbox_confirmation='pending', notifications=count,
                          attempt_ids=[str(a['id']) for a in list_attempts()])
    except Exception as exc:
        report.update(status='failed_or_uncertain_do_not_resend', error_type=type(exc).__name__)
        if run_id:
            fail_pipeline_run(run_id, 'notifying', exc)
    finally:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': report['passed'], 'status': report['status'], 'report': str(args.output)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
