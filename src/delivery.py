"""Durable external-send boundary and explicit operator reconciliation.

An attempt is ambiguous before invoking the transport. No automatic resend is
allowed until success is recorded or an operator resolves it with evidence.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from src.tracker import get_conn, pipeline_execution_lock


class DeliveryAmbiguous(RuntimeError):
    pass


def list_attempts(limit: int = 20) -> list[dict]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM delivery_attempts ORDER BY created_at DESC LIMIT %s", (limit,))
        return [dict(row) for row in cur.fetchall()]


def prepare_attempt(job_ids: list[str], run_id: str) -> dict:
    import psycopg2
    attempt_id = uuid4()
    message_id = f"<job-agent-{attempt_id}@job-agent.local>"
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO delivery_attempts (id, run_id, job_ids, message_id, status)
                VALUES (%s, %s, %s, %s, 'ambiguous') RETURNING *""",
                        (attempt_id, UUID(run_id), [UUID(j) for j in job_ids], message_id))
            return dict(cur.fetchone())
    except psycopg2.errors.UniqueViolation:
        raise DeliveryAmbiguous("Unresolved delivery exists; inspect and reconcile before sending") from None


def finish_attempt(attempt_id: str, *, sent: bool, reason: str) -> int:
    """Atomically resolve the attempt and record all successful job deliveries."""
    inserted = 0
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM delivery_attempts WHERE id = %s FOR UPDATE", (UUID(attempt_id),))
        attempt = cur.fetchone()
        if not attempt or attempt["status"] != "ambiguous":
            raise ValueError("Attempt does not exist or is already resolved")
        if sent:
            for job_id in attempt["job_ids"]:
                cur.execute("""INSERT INTO notifications (job_id, run_id, channel, status)
                    VALUES (%s, %s, 'email', 'sent') ON CONFLICT (job_id, channel) DO NOTHING
                    RETURNING id""", (job_id, attempt["run_id"]))
                inserted += int(cur.fetchone() is not None)
                cur.execute("UPDATE jobs SET system_state = 'notified' WHERE id = %s", (job_id,))
        cur.execute("""UPDATE delivery_attempts SET status = %s, resolved_at = NOW(),
            resolution_reason = %s WHERE id = %s""",
                    ("sent" if sent else "not_sent", reason, UUID(attempt_id)))
    return inserted


def deliver_digest(jobs: list[dict], *, run_id: str, send) -> int:
    if not jobs:
        # Even an empty digest must surface unresolved delivery for operations.
        if any(a["status"] == "ambiguous" for a in list_attempts(100)):
            raise DeliveryAmbiguous("Unresolved delivery exists; reconcile before completing")
        return 0
    attempt = prepare_attempt([str(j["id"]) for j in jobs], run_id)
    try:
        sent = send(jobs, message_id=attempt["message_id"])
    except Exception:
        raise DeliveryAmbiguous(f"Digest delivery uncertain; reconcile attempt {attempt['id']}") from None
    if not sent:
        raise DeliveryAmbiguous(f"Digest delivery failed or uncertain; reconcile attempt {attempt['id']}")
    # If this transaction fails (or process dies), the committed ambiguous record
    # remains and prevents resend. Message-ID is an investigation aid, not dedupe.
    return finish_attempt(str(attempt["id"]), sent=True, reason="Transport acknowledged send")


def reconcile(attempt_id: str, *, sent: bool, reason: str, workers_stopped: bool) -> int:
    if not workers_stopped:
        raise ValueError("Stop workers and trigger entrypoints before reconciliation")
    if not 10 <= len(reason.strip()) <= 1000:
        raise ValueError("Record 10 to 1000 characters of reconciliation evidence")
    with pipeline_execution_lock():
        return finish_attempt(attempt_id, sent=sent, reason=reason.strip())


def main(argv=None) -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    resolve = sub.add_parser("reconcile")
    resolve.add_argument("attempt_id", type=UUID)
    resolve.add_argument("--outcome", choices=("sent", "not-sent"), required=True)
    resolve.add_argument("--reason", required=True)
    resolve.add_argument("--confirm-workers-stopped", action="store_true", required=True)
    args = parser.parse_args(argv)
    if args.command == "list":
        print(json.dumps(list_attempts(), default=str, indent=2))
    else:
        reconcile(str(args.attempt_id), sent=args.outcome == "sent", reason=args.reason,
                  workers_stopped=args.confirm_workers_stopped)
        print("Delivery reconciled; no email sent by this command")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
