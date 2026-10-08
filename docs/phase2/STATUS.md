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
| Stage 2 deterministic ranking | explainable baseline scorer | 30-job gold set, Precision@5, pairwise accuracy | Complete |
| Semantic ranking implementation | model-backed component scoring behind same RankingResult contract | mocked contract/prompt-injection tests | Complete, disabled by default |
| Semantic promotion gate | candidate-vs-baseline live evaluator | exits non-zero on Precision@5 or pairwise regression | Ready for live run |
| Rank-before-generate | only shortlisted jobs receive CV generation | E2E acceptance test | Complete |
| CV generation contract | typed result, no ranking responsibility, prompt-injection boundary | CV agent unit tests | Complete |
| CV factuality | exact evidence references + unsupported numeric/magnitude claim blocking | CV factuality goldens | Complete |
| CV audit history | prompt/model/profile/source CV fingerprint/evidence/validation/usage persisted | DB integration test | Complete |
| Job recovery | persisted job system state recovers unfinished work across runs | failed-tailoring retry E2E test | Complete |
| Notification idempotency | persisted exactly-once job/channel delivery | integration + E2E rerun tests | Complete |
| API write security | bearer token for writes and manual trigger | API security regression tests | Complete |
| HTML/link safety | escaped dashboard/email output; unsafe URL schemes blocked | XSS regression tests | Complete |
| Security headers | CSP, frame denial, nosniff, referrer policy | API header test | Complete |
| End-to-end acceptance | mocked complete pipeline + failure injection | CI E2E harness | Complete |
| Source health telemetry | per-source persisted counts and consecutive-zero warning events | DB integration tests | Complete |
| Model usage/cost telemetry | ranking/CV tokens persisted per artifact and run; cost rates configurable | unit + DB integration assertions | Complete |
| Live provider smoke | one semantic rank + one evidence-gated CV, no DB/email side effects | explicit opt-in command | Ready for live run |

## Current Phase 2 runtime flow

```text
discover
  -> validate source contract
  -> canonicalize / deduplicate
  -> persist (system_state=discovered)
  -> deterministic eligibility
      -> filtered_out OR continue
  -> ranking
      deterministic by default
      semantic only when explicitly enabled
      -> ranked_out OR shortlisted
  -> evidence-constrained CV generation
      -> on failure: remain shortlisted for retry
      -> on success: tailored
  -> exactly-once notification
      -> on delivery failure: remain tailored for retry
      -> on success: notified
```

## Recovery semantics

Phase 2 does not depend on in-memory progress.

Jobs carry persisted processing state:

- `legacy`
- `discovered`
- `filtered_out`
- `ranked_out`
- `shortlisted`
- `tailored`
- `notified`

A later run processes unfinished states. A process crash after persistence,
ranking, CV generation, or before delivery therefore does not permanently
strand the job.

## Ranking promotion policy

Production defaults to:

```text
RANKING_MODE=deterministic
```

The semantic implementation exists but is not automatically promoted.

Before changing production to:

```text
RANKING_MODE=semantic
```

run:

```bash
python -m evals.live_provider_smoke
python -m evals.run_semantic_eval
```

The first command performs one ranking and one CV-generation call without DB or
email side effects. The second evaluates the candidate semantic model on the
same 30-job labelled benchmark as the deterministic baseline and exits non-zero
if Precision@5 or pairwise preference accuracy regresses.

## Remaining external validation

The code hardening work is complete enough for Phase 2 acceptance. Two
provider-dependent checks remain intentionally manual:

1. run the controlled live-provider smoke with real credentials;
2. run the 30-job semantic promotion evaluation and inspect quality/cost before
   enabling semantic ranking.

Those checks require real provider credentials and incur real model calls, so
they are deliberately excluded from automatic pull-request CI.
