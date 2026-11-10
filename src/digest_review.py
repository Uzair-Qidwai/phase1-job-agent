"""Saved preview → explicit approval → durable one-shot delivery.

Review data is private. No command other than `send` contacts Gmail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from psycopg2.extras import Json

from src import tracker
from src.cv_agent import _load_master_cv
from src.emailer import _build_html, send_snapshot
from src.settings import get_settings


def fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def get_batch(batch_id: str) -> dict:
    with tracker.get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM digest_batches WHERE id = %s", (UUID(batch_id),))
        row = cur.fetchone()
    if not row:
        raise ValueError("Review batch not found")
    return dict(row)


def list_batches(limit: int = 20) -> list[dict]:
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be 1–100")
    with tracker.get_conn() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id, status, fingerprint, created_at, approved_at,
            snapshot->>'recipient' AS recipient,
            jsonb_array_length(snapshot->'jobs') AS job_count
            FROM digest_batches ORDER BY created_at DESC, id DESC LIMIT %s""", (limit,))
        return [dict(r) for r in cur.fetchall()]


def _current_jobs(job_ids: list[str], *, observed_summaries: bool = True, qualifications: bool = False) -> list[dict]:
    from src.cv_changes import describe_changes
    source = _load_master_cv()
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    with tracker.get_conn() as conn, conn.cursor() as cur:
        cur.execute("""SELECT j.id, j.title, j.company, j.location, j.url, j.source,
            j.match_score, j.system_state, j.cv_version_id, j.description,
            cv.tailored_cv, cv.source_cv_sha256, cv.validation,
            EXISTS (SELECT 1 FROM notifications n WHERE n.job_id=j.id
                    AND n.channel='email' AND n.status='sent') AS notified
            FROM jobs j LEFT JOIN cv_versions cv ON cv.id=j.cv_version_id
            WHERE j.id = ANY(%s::uuid[])""", (job_ids,))
        by_id = {str(r['id']): dict(r) for r in cur.fetchall()}
    result = []
    for job_id in job_ids:
        row = by_id.get(job_id)
        if (not row or row['notified'] or row['system_state'] != 'tailored'
                or row['match_score'] is None or not row['tailored_cv'] or (row['validation'] or {}).get('valid') is not True
                or row['source_cv_sha256'] != source_hash):
            raise ValueError("Jobs or source CV changed, are unvalidated, or already sent; prepare a new batch")
        changes = describe_changes(source, row["tailored_cv"])
        item = {
            **{k: row[k] for k in ('title', 'company', 'location', 'url', 'source', 'description')},
            'id': job_id, 'match_score': float(row['match_score']),
            'cv_version_id': str(row['cv_version_id']),
            'cv_text': row['tailored_cv'], 'source_cv_sha256': row['source_cv_sha256'],
            # Model commentary is not evidence-validated. Keep it out of reviewed mail.
            'changes_made': (changes['summary'] if observed_summaries else
                             'CV preview available for review; qualifications require verification.'),
        }
        if observed_summaries:
            item['observed_changes'] = changes
        if qualifications:
            from src.qualifications import assess_qualifications
            item['qualifications'] = assess_qualifications(row['description'], source)
        result.append(item)
    return result


def _validate(batch: dict, expected: str) -> None:
    if expected != batch['fingerprint'] or fingerprint(batch['snapshot']) != expected:
        raise ValueError("Preview fingerprint changed; review the saved batch again")
    settings = get_settings()
    snap = batch['snapshot']
    if (settings.gmail_sender, settings.digest_recipient) != (snap['sender'], snap['recipient']):
        raise ValueError("Sender or recipient changed; cancel and prepare a new batch")
    if snap.get('version') not in {1, 2, 3}:
        raise ValueError('Unknown preview version; prepare a new batch')
    if _current_jobs([j['id'] for j in snap['jobs']],
                     observed_summaries=snap['version'] >= 2, qualifications=snap['version'] >= 3) != snap['jobs']:
        raise ValueError("Job or CV preview changed; cancel and prepare a new batch")


def _prepare_batch(job_ids: list[str] | None = None, *, limit: int = 5) -> dict | None:
    """Caller holds the pipeline execution lock, including from the scheduler."""
    if job_ids is not None:
        job_ids = [str(UUID(str(job_id))) for job_id in job_ids]
    if not 1 <= limit <= 20:
        raise ValueError("Batch size must be 1–20")
    with tracker.get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM digest_batches WHERE status IN ('pending','approved','sending')")
        existing = cur.fetchone()
    if existing:
        if job_ids is not None and set(job_ids) != {j['id'] for j in existing['snapshot']['jobs']}:
            raise ValueError("An open batch already exists; send or cancel it first")
        if existing['status'] == 'sending':
            raise ValueError("Delivery unresolved; reconcile it before preparing another batch")
        _validate(dict(existing), existing['fingerprint'])
        return dict(existing)
    settings = get_settings()
    if job_ids is None:
        jobs = tracker.get_new_jobs_for_digest(min_score=settings.shortlist_threshold)
        jobs.sort(key=lambda j: (-float(j['match_score']), str(j['id'])))
        job_ids = [str(j['id']) for j in jobs[:limit]]
    if not job_ids:
        return None
    if len(job_ids) > 20 or len(set(job_ids)) != len(job_ids):
        raise ValueError("Select 1–20 distinct jobs")
    if not settings.gmail_sender or not settings.digest_recipient:
        raise ValueError("Configure sender and recipient before preparing a preview")
    if any(c in settings.gmail_sender + settings.digest_recipient for c in '\r\n'):
        raise ValueError("Invalid email address")
    jobs = _current_jobs(job_ids, qualifications=True)
    snapshot = {'version': 3, 'sender': settings.gmail_sender,
                'recipient': settings.digest_recipient, 'jobs': jobs,
                'subject': f"📋 Job Digest — {len(jobs)} role{'s' if len(jobs) != 1 else ''} for review",
                'html': _build_html(jobs, reviewed=True)}
    with tracker.get_conn() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO digest_batches(id,snapshot,fingerprint)
            VALUES (%s,%s,%s) RETURNING *""", (uuid4(), Json(snapshot), fingerprint(snapshot)))
        return dict(cur.fetchone())


def prepare_batch(job_ids: list[str] | None = None, *, limit: int = 5) -> dict | None:
    with tracker.pipeline_execution_lock():
        return _prepare_batch(job_ids, limit=limit)


def approve_batch(batch_id: str, expected: str) -> dict:
    with tracker.pipeline_execution_lock():
        batch = get_batch(batch_id)
        if batch['status'] not in {'pending', 'approved'}:
            raise ValueError("Only a pending batch can be approved")
        _validate(batch, expected)
        with tracker.get_conn() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE digest_batches SET status='approved',
                approved_fingerprint=fingerprint, approved_at=NOW() WHERE id=%s""", (UUID(batch_id),))
        return get_batch(batch_id)


def cancel_batch(batch_id: str) -> None:
    with tracker.pipeline_execution_lock(), tracker.get_conn() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE digest_batches SET status='cancelled', approved_fingerprint=NULL,
            approved_at=NULL WHERE id=%s AND status IN ('pending','approved') RETURNING id""",
                    (UUID(batch_id),))
        if not cur.fetchone():
            raise ValueError("Only a pending or approved batch can be cancelled")


def send_batch(batch_id: str, expected: str, *, transport=None) -> int:
    from src.delivery import prepare_attempt, send_prepared_attempt
    transport = transport or send_snapshot
    with tracker.pipeline_execution_lock():
        batch = get_batch(batch_id)
        if batch['status'] != 'approved' or batch['approved_fingerprint'] != expected:
            raise ValueError("Batch is not approved for this preview or was already sent")
        _validate(batch, expected)
        run_id = tracker.start_pipeline_run('manual')
        try:
            tracker.update_pipeline_run(run_id, status='notifying', current_stage='notifying')
            # State and attempt commit together. A crash cannot leave approval reusable.
            with tracker.get_conn() as conn, conn.cursor() as cur:
                attempt = prepare_attempt([j['id'] for j in batch['snapshot']['jobs']], run_id, conn=conn)
                cur.execute("""UPDATE digest_batches SET status='sending', attempt_id=%s
                    WHERE id=%s""", (attempt['id'], UUID(batch_id)))
            tracker.record_pipeline_event(run_id, 'approved_digest_send', stage='notifying',
                                          payload={'batch_id': batch_id, 'fingerprint': expected})
            def send(jobs, **kwargs):
                return transport(batch['snapshot'], **kwargs)
            count = send_prepared_attempt(attempt, batch['snapshot']['jobs'], send=send)
            tracker.complete_pipeline_run(run_id, jobs_notified=count)
            return count
        except Exception as exc:
            tracker.fail_pipeline_run(run_id, 'notifying', exc)
            raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--job-id', action='append')
    prepare.add_argument('--limit', type=int, default=5)
    for command in ('preview', 'approve', 'send', 'cancel'):
        child = sub.add_parser(command)
        child.add_argument('batch_id', type=UUID)
        if command in ('approve', 'send'):
            child.add_argument('--fingerprint', required=True)
        if command == 'preview':
            child.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'list':
        result = list_batches()
    elif args.command == 'prepare':
        batch = prepare_batch(args.job_id, limit=args.limit)
        result = {k: batch[k] for k in ('id','status','fingerprint')} if batch else {'jobs': 0}
    elif args.command == 'preview':
        batch = get_batch(str(args.batch_id))
        # Private bundle includes exact email and local CV previews, never attachments.
        args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        files = {'email.html': batch['snapshot']['html'],
                 'review.json': json.dumps(batch, default=str, indent=2)}
        for i, job in enumerate(batch['snapshot']['jobs'], 1):
            files[f'cv-{i}.md'] = job['cv_text']
        for name, content in files.items():
            path = args.output / name
            with path.open('x') as stream:
                path.chmod(0o600)
                stream.write(content)
        result = {'output': str(args.output), 'fingerprint': batch['fingerprint'],
                  'recipient': batch['snapshot']['recipient']}
    elif args.command == 'approve':
        batch = approve_batch(str(args.batch_id), args.fingerprint)
        result = {'status': batch['status']}
    elif args.command == 'send':
        result = {'jobs_notified': send_batch(str(args.batch_id), args.fingerprint)}
    else:
        cancel_batch(str(args.batch_id))
        result = {'status': 'cancelled'}
    print(json.dumps(result, default=str, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
