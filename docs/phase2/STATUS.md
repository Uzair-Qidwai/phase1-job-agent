# Phase 2 Engineering Status

This document tracks implementation against the Phase 2 architecture and evaluation plan.

Updated for Checkpoint 3 specialist-workflow implementation. The former recovery
checkpoint is preserved in [RECOVERY_CHECKPOINT.md](RECOVERY_CHECKPOINT.md).
[Checkpoint 4](CHECKPOINT_04.md) is the planned live-validation/exit milestone. Automated checks pass;
Phase 2 exit approval is still pending. See [acceptance report](ACCEPTANCE.md).

| Workstream | Runtime implementation | Evaluation / test gate | Status |
|---|---|---|---|
| Configuration | Central validated settings for DB, model, Gmail, API, scheduler | settings validation tests | Complete |
| Job identity | Source-aware canonical URLs and native source IDs | golden identity fixtures; Indeed regression test | Complete |
| Database hardening | constraints plus ordered checksum migration ledger | legacy adoption, repeatability, concurrent runners, rollback and history-drift tests | Automated checks pass |
| Pipeline locking | database admission plus worker execution lock and one-time HTTP reservation claim | concurrent HTTP, worker-lifetime and process-death tests | Automated checks pass |
| Stranded-run recovery | explicit worker-stop confirmation, execution lock, audited stage-preserving failure | process termination, live-worker refusal, late-child and temporary-contention tests | Implemented; operator shutdown required |
| Operational reads | bounded run/source-health history and run details | validation, filtering, pagination and redaction tests | Automated checks pass |
| Run observability | stage, counts, duration, errors, event ledger | integration + E2E assertions | Complete |
| Source adapters | common adapter contract and RawJob runtime validation | source contract tests | Complete |
| Candidate profile | versioned structured matching profile | profile load/validation tests | Complete |
| Stage 1 filtering | explicit conservative hard filters | eligibility golden fixtures | Complete |
| Stage 2 deterministic ranking | explainable baseline scorer | 30-job gold set, Precision@5, pairwise accuracy | Complete |
| Semantic ranking implementation | model-backed component scoring behind same RankingResult contract | mocked contract/prompt-injection tests | Complete, disabled by default |
| Semantic promotion gate | candidate-vs-baseline live evaluator | exits non-zero on Precision@5 or pairwise regression | Ready for live run |
| Rank-before-generate | only shortlisted jobs receive CV generation | E2E acceptance test | Complete |
| CV generation contract | typed result, no ranking responsibility, prompt-injection boundary | CV agent unit tests | Complete |
| CV factuality | whole-output lexical coverage, source quotes, numeric support, qualifiers and negation | v2 adversarial factuality goldens | Deterministic gate passes; semantic limits remain |
| CV audit history | prompt/model/profile/source CV fingerprint/evidence/validation/usage persisted | DB integration test | Complete |
| Job recovery | persisted job system state recovers unfinished work across runs | failed-tailoring retry E2E test | Complete |
| Notification idempotency | recorded job/channel delivery suppresses later digests | integration + E2E rerun tests | Passes recorded-delivery tests; external-send crash window remains |
| API write security | bearer token for writes and manual trigger | API security regression tests | Complete |
| HTML/link safety | escaped dashboard/email output; unsafe URL schemes blocked | XSS regression tests | Complete |
| Security headers | CSP, frame denial, nosniff, referrer policy | API header test | Complete |
| End-to-end acceptance | mocked complete pipeline + failure injection | CI E2E harness | Automated checks pass; live acceptance pending |
| Source health telemetry | per-source persisted counts and consecutive-zero warning events | DB integration tests | Complete |
| Model usage/cost telemetry | ranking/CV tokens persisted per artifact and run; cost rates configurable | unit + DB integration assertions | Complete |
| Live provider smoke | one semantic rank + one evidence-gated CV, no DB/email side effects | explicit opt-in command | Ready for live run |

## Checkpoint 3 specialist addition

- Provider-independent Agents SDK runtime with OpenAI, Anthropic and Gemini routing.
- Per-role explicit models and price configuration; no automatic vendor fallback.
- Opt-in researcher/analyst/writer/reviewer workflow, with bounded revisions.
- Deterministic CV gate enforced after every draft regardless of reviewer approval.
- Sanitized role execution events and persisted review metadata; failed/rejected
  work remains accounted for. Unknown costs are explicitly incomplete.
- Provider routing and SDK tool loops are tested offline, not live-certified.

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
  -> notification with persisted duplicate suppression
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

A later run processes unfinished job states, but an abrupt process death can
leave its run active and prevent later admission. Follow [the recovery
runbook](OPERATIONS.md) to verify worker shutdown, mark the stranded run failed,
and retry from its persisted stage. Recovery must not infer death from age.

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

The first command performs ranking and CV generation without DB or email side
effects. With `AGENT_WORKFLOW_ENABLED=true` it runs all four specialists, including
bounded tool loops and possible revisions, so it can make multiple model calls. The second evaluates the candidate semantic model on the
same 30-job labelled benchmark as the deterministic baseline and exits non-zero
if Precision@5 or pairwise preference accuracy regresses.

## Remaining external validation

Phase 2 acceptance is not yet approved. Two provider-dependent checks are
pending at the user’s request while credentials and cost rates are unavailable:

1. run the controlled live-provider smoke with selected role/provider credentials;
2. run the 30-job semantic promotion evaluation and inspect quality/cost before
   enabling semantic ranking.

Those checks require real provider credentials and incur real model calls, so
they are deliberately excluded from automatic pull-request CI.

Additional exit decisions: accept or remediate external email delivery ambiguity,
CV semantic/context limitations, and private-network unauthenticated reads.
Neither this status document nor passing CI constitutes approval to merge.
