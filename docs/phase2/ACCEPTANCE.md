# Phase 2 acceptance review — recovery baseline

Date: 2026-10-08. Branch: `phase2-foundation`. PR #1 stays Draft.

**Disposition: automated checks pass; live validation and exit approval remain
pending. This report is not authorization to merge or enable semantic ranking.**

## Current milestone map

This report preserves recovery-baseline evidence. The user reassigned Checkpoint 3
to the agent-workflow addition: [Checkpoint 3](CHECKPOINT_03.md) now records the
completed provider/specialist implementation and CI #264 (150 tests). Its live
promotion remains pending. The former checkpoint record is
[RECOVERY_CHECKPOINT.md](RECOVERY_CHECKPOINT.md).

[Checkpoint 4](CHECKPOINT_04.md) is the final live-validation, remaining-features
and exit-review milestone. It remains unstarted, and no earlier offline results
constitute live validation or permission to merge.

## Evidence

- Full local regression suite: 125 passed against isolated PostgreSQL.
- Implementation `81aa579` passed [CI #258](https://github.com/Uzair-Qidwai/phase1-job-agent/actions/runs/37738157620)
  on Python 3.11/PostgreSQL 16, including the offline acceptance report.
- Deterministic ranking: 30 labelled jobs, Precision@5 = 1.0, pairwise accuracy = 1.0.
- CV factuality: all 22 golden cases matched their expected valid/invalid outcomes.
- The ranking/CV report is [saved here](../../evals/reports/phase2_checkpoint03.json),
  including dataset hashes. Reproduce with `python -m evals.run_offline_eval`;
  this command also runs in CI. These are fixture metrics, not estimates of
  real-world accuracy or model quality.
- Worker recovery tests exercise an actual terminated process, a live pipeline
  holding its lock through scraping, blocked competing workers, late admitted
  children, temporary lock contention, explicit confirmation and audit history.
- Existing tests cover HTTP admission, one-time reservation claims, migration
  adoption/repeatability/order/drift/rollback/concurrency, operational reads,
  generation validation, and stage-aware retry without repeated scraping.

## Acceptance mapping

| Workstream | Evidence / current behavior | Remaining qualification |
| --- | --- | --- |
| Foundation/configuration | clean install, lint, credential-independent tests, CI | live service configuration still pending |
| Job identity | native source IDs and URL canonicalization goldens; DB uniqueness | live source changes are outside fixture guarantees |
| Run ledger/admission/recovery | durable unique slot, per-stage history, execution lock, audited operator recovery | operators must verify shutdown; no automatic expiry or distributed fencing |
| Source adapters | common RawJob contract and source-specific adapters | no live scraping was performed in this validation |
| Profile/ranking | explainable deterministic ranking and 30-job benchmark | semantic mode remains disabled pending live promotion eval |
| CV generation | typed output, v2 whole-output lexical coverage, complete evidence quotes, persisted metadata | real-provider smoke and semantic/context review pending; valid paraphrases may fail |
| CV failure retry | failed generation leaves work shortlisted for a later run | no general application-level immediate retry/backoff policy |
| Notification/API | committed delivery suppresses duplicate digests; protected mutations; safe HTML/URLs; bounded read responses | external send/DB commit ambiguity; reads require private network |
| End-to-end | mocked external boundaries and fault injection | automated results do not establish live operational acceptance |

## Operator recovery delivered

[OPERATIONS.md](OPERATIONS.md) specifies shutdown verification, provider-state
review, exact-run recovery, and a separate retry. `python -m src.recovery` requires
`--confirm-workers-stopped` and an audit reason. It refuses live execution locks
and terminal/missing runs. Successful recovery atomically records failure and
an audit event while preserving the failed stage. Recovery never sends email.

Deployment must stop old workers before adopting the lock protocol. Workers need
a direct/session-pooled PostgreSQL connection, not transaction pooling. A lost
DB connection cannot establish that a worker stopped, so the confirmation is an
operational prerequisite, not an automatic liveness inference.

## Still pending, not silently accepted

1. **Live-provider smoke:** deferred at the user's request; this checkout has no
   configured model credential or cost rates. Run the controlled smoke once
   configured, inspect the generated result and factuality rejections, and save
   measured usage/latency plus configured-price cost estimates. No provider calls
   were made during this checkpoint.
2. **Semantic promotion:** run the existing 30-job live comparison before enabling
   semantic ranking. Deterministic ranking remains the default meanwhile.
3. **Email ambiguity:** if sending succeeds and the worker dies before recording
   delivery, retry can resend. Inspect provider records before a notifying-stage
   recovery/retry. A reconciliation mechanism or explicit acceptance of this
   limitation is still needed; database uniqueness does not provide exactly-once
   external delivery.
4. **CV semantic limits:** copying/reordering or lexical overlap can still alter
   relationships or section context. Human review remains necessary.
5. **Exit decision:** review these limitations, the private-network read policy,
   migration deployment assumptions and deferred retry policy before marking the
   PR ready. No merge has been performed or approved.

## Checkpoint 4 offline readiness

Delivery reconciliation, run-wide request/spend controls, bounded transient retry,
CV relationship/section checks and live-test tooling are implemented. Existing
worker-death/recovery and concurrent trigger checks remain green. Disposable DB
backup/restore was rehearsed; production data/host deployment was not touched.

See [LIVE_TESTING.md](LIVE_TESTING.md) for the staged commands and remaining gates.
Live model/source quality, actual email delivery, target-host deployment and human
CV acceptance remain **pending**. Checkpoint 4 is not an exit approval.
