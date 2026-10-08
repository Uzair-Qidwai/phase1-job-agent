# Phase 2 Engineering Status

This document tracks implementation against the Phase 2 architecture and evaluation plan.

| Workstream | Runtime implementation | Evaluation / test gate | Status |
|---|---|---|---|
| Configuration | Central validated settings for DB, model, Gmail, API, scheduler | settings validation tests | Complete |
| Job identity | Source-aware canonical URLs and native source IDs | golden identity fixtures; Indeed regression test | Complete |
| Database hardening | constraints, source identity, run/events, notifications, CV audit metadata, job system state | migrations executed twice in CI | Complete |
| Pipeline locking | one active run across processes | PostgreSQL integration test | Complete |
| Run observability | stage, counts, duration, errors, event ledger | integration + E2E assertions | Complete |
| Source adapters | common adapter contract and RawJob runtime validation | source contract tests | Complete |
| Candidate profile | versioned structured matching profile | profile load/validation tests | Complete |
| Stage 1 filtering | explicit conservative hard filters | eligibility golden fixtures | Complete |
| Stage 2 ranking | explainable deterministic baseline | ranking goldens, Precision@K, pairwise accuracy | Baseline complete |
| Semantic ranking | model-backed semantic component scoring | candidate-vs-baseline eval required before activation | Pending |
| Rank-before-generate | only shortlisted jobs receive CV generation | E2E acceptance test | Complete |
| CV generation contract | typed result, no ranking responsibility, prompt-injection boundary | CV agent unit tests | Complete |
| CV factuality | exact evidence references + unsupported numeric-claim blocking | CV factuality goldens | Complete |
| CV audit history | prompt/model/profile/source CV fingerprint/evidence/validation persisted | DB integration test | Complete |
| Job recovery | persisted job system state recovers unfinished work across runs | failed-tailoring retry E2E test | Complete |
| Notification idempotency | persisted exactly-once job/channel delivery | integration + E2E rerun tests | Complete |
| API write security | bearer token for writes and manual trigger | API security regression tests | Complete |
| HTML/link safety | escaped dashboard/email output; unsafe URL schemes blocked | XSS regression tests | Complete |
| Security headers | CSP, frame denial, nosniff, referrer policy | API header test | Complete |
| End-to-end acceptance | mocked complete pipeline + failure injection | CI E2E harness | Complete |
| Source health telemetry | per-source discovery counts logged | persistent thresholds/alerts not yet implemented | Partial |
| Model usage/cost telemetry | CV version records model identity | token/cost accounting not yet implemented | Pending |
| Ranking golden set | initial strong/borderline/weak benchmark | deterministic CI | Initial set complete; expand before semantic rollout |

## Current Phase 2 runtime flow

```text
discover
  -> validate source contract
  -> canonicalize / deduplicate
  -> persist (system_state=discovered)
  -> deterministic eligibility
      -> filtered_out OR continue
  -> explainable ranking
      -> ranked_out OR shortlisted
  -> evidence-constrained CV generation
      -> on failure: remain shortlisted for retry
      -> on success: tailored
  -> exactly-once notification
      -> on delivery failure: remain tailored for retry
      -> on success: notified
```

## Recovery semantics

Phase 2 does not depend on an in-memory notion of progress.

Jobs carry their own persisted processing state:

- `legacy`
- `discovered`
- `filtered_out`
- `ranked_out`
- `shortlisted`
- `tailored`
- `notified`

A later run processes unfinished states. This means a process crash after persistence, ranking, CV generation, or before delivery does not permanently strand the job.

## Remaining hardening before calling Phase 2 complete

1. expand the ranking benchmark beyond the initial golden set;
2. implement semantic ranking behind the existing `RankingResult` contract;
3. compare semantic ranking against deterministic baseline before activation;
4. persist source-health metrics and define failure thresholds;
5. record LLM token usage and estimated cost;
6. run a controlled live smoke test with real providers after deterministic CI is green.

These remaining items do not require a rewrite of the architecture already implemented.
