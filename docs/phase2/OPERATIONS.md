# Pipeline recovery runbook

## Inspect first

Use the read-only `GET /pipeline/runs` and `GET /pipeline/runs/{uuid}` endpoints
to identify the exact active run and its stage. A quiet or old run is not proof
that its worker is dead. There is deliberately no automatic age-based unlock.

## Recover a stranded active run

1. Stop API trigger entrypoints, the scheduler, and every manual/child pipeline
   process on every host connected to this database. Check the process manager
   and verify termination. Merely closing a terminal or losing a DB connection
   is insufficient. Keep entrypoints stopped throughout recovery.
2. If the last stage was `notifying`, inspect provider delivery records before
   retrying: an email may have sent before the database recorded success. Do not
   blindly retry an ambiguous delivery. Resolve the ambiguity first; the command
   below does not send email or reconcile delivery records.
3. From the matching source checkout and configured database environment, run:

   ```bash
   python -m src.recovery RUN_UUID \
     --confirm-workers-stopped \
     --reason "Verified all workers stopped after host failure; incident reference"
   ```

   Replace `RUN_UUID` with the exact active run UUID. Do not include secrets or
   personal data in the reason; it is stored in the internal audit history.
4. The command acquires the same PostgreSQL execution lock used by workers. A
   healthy running worker causes immediate refusal, even with the confirmation
   flag. Missing or already terminal run IDs cause refusal without mutation.
5. Success marks only that run `failed`, preserves its failed stage, sets a finish
   time, and records an `operator_recovery` event and operator-supplied reason in
   one transaction. It does not delete jobs or launch another process.
6. Review the failed run and provider state. Once safe, use the existing retry:

   ```bash
   python -m src.scheduler --retry-run RUN_UUID
   ```

   Or restart the API and use its authenticated retry endpoint. Resume scheduling
   after confirming retry results. The normal unique active-run index still
   arbitrates all admissions.

## Why both the confirmation and the lock?

A session-level database lock prevents recovery racing a connected live worker.
It is held for the entire pipeline, including child reservation claim and startup.
Admitted children wait for temporary contention; if their reservation was
recovered, they refuse to execute it after acquiring the lock. The active-run
row remains the durable admission guard after process death releases its session.

A disconnected database session is not proof that the worker process has ended.
A network-partitioned process may still perform an external action. Recovery
therefore requires an actual operator-verified stop, not just an absent lock.
Older workers from before this protocol do not hold this lock: stop all old
workers before deploying it or using recovery. This is an operator procedure,
not an automatic lease/heartbeat system or distributed fencing guarantee.

Use a direct PostgreSQL connection or session-pooling connection for workers;
transaction-pooling proxies cannot preserve this session-lock contract.
Each running worker holds one additional database connection for the lock.

## Delivery ambiguity and reconciliation

Every non-empty digest commits an `ambiguous` delivery attempt **before** calling
Gmail. Success atomically records all job notifications and resolves the attempt.
A crash, false return, provider error or failed final DB commit leaves the attempt
unresolved. All subsequent digests are blocked until an operator investigates.
This favors avoiding duplicate mail over unattended retry availability.

Stop all workers/entrypoints first and inspect:

```bash
python -m src.delivery list
```

Use the recorded Message-ID to investigate Gmail Sent/provider logs. It is a
correlation aid, not an exactly-once guarantee. If confirmed sent:

```bash
python -m src.delivery reconcile ATTEMPT_UUID --outcome sent \
  --reason "Verified delivery in provider logs; incident reference" \
  --confirm-workers-stopped
```

Only with evidence that nothing was sent, use `--outcome not-sent`. That releases
the block and leaves jobs eligible for a later pipeline retry. If inconclusive,
leave ambiguous and investigate; do not guess. The command sends no email, holds
the worker exclusion lock and stores the resolution reason. Then recover any
stranded run and retry from its persisted stage. Successful CV deliveries remain
recorded when a different CV failed; retry resumes tailoring without resending.

See [live-test handoff](LIVE_TESTING.md) for budgets, privacy and deployment checks.
