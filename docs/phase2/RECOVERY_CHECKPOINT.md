# Recovery baseline — formerly Checkpoint 3

Date: 2026-10-08. Continues Checkpoint 2 (`0212abf`, CI #256).
Branch `phase2-foundation`; PR #1 remains Draft. No changes to `main`.

## Implemented

- PostgreSQL session execution lock held through every worker's pipeline lifetime.
- Manual recovery CLI with worker-stop confirmation, exact run UUID and audit reason.
- Live-worker exclusion, atomic stage-preserving failure/audit event, and refusal
  of terminal/missing runs. Recovery and retry are distinct operations.
- Admitted children acquire the lock before claiming; late children cannot run a
  recovered reservation, and temporary lock contention does not discard a child.
- Operator runbook covering deployment, process verification, connection pooling,
  network partitions, and external email ambiguity.
- Reconciled status/architecture/evaluation docs: duplicate suppression after a
  recorded send is not an exactly-once delivery guarantee.
- Reproducible offline acceptance report and CI evaluator.

## Verification

Local suite: 125 passed. Offline ranking: Precision@5 1.0 and pairwise accuracy
1.0 over 30 fixture jobs. CV goldens: 22/22 matched expected outcomes.
Implementation commit `81aa5799800bf5ed43bdec2df5b3a10d2f264b73` passed
[CI #258](https://github.com/Uzair-Qidwai/phase1-job-agent/actions/runs/37738157620),
including migrations, lint, 125 tests and offline acceptance metrics.

See [ACCEPTANCE.md](ACCEPTANCE.md) for the evidence mapping and open decisions.
Live provider and semantic promotion checks remain pending at the user's request;
credentials/cost rates were not configured. No live model calls, scraping, or
email sends were performed. This checkpoint does not approve Phase 2 exit.

Milestone numbering was revised by the user: Checkpoint 3 now covers the agent
workflow addition; Checkpoint 4 covers live validation and Phase 2 exit. This
record preserves the earlier recovery work and its CI evidence.
