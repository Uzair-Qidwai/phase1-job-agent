# Phase 2 Engineering Status

This document tracks implementation against the Phase 2 architecture and evaluation plan.

Updated for Checkpoint 4 offline hardening and live-test preparation. The former recovery
checkpoint is preserved in [RECOVERY_CHECKPOINT.md](RECOVERY_CHECKPOINT.md).
[Checkpoint 4](CHECKPOINT_04.md) has completed offline preparation; live validation/exit remains pending. Automated checks pass;
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
| Semantic promotion gate | candidate-vs-baseline live evaluator | exits non-zero on Precision@5 or pairwise regression | Live checks recorded in Checkpoint 5 |
| Rank-before-generate | only shortlisted jobs receive CV generation | E2E acceptance test | Complete |
| CV generation contract | typed result, no ranking responsibility, prompt-injection boundary | CV agent unit tests | Complete |
| CV factuality | whole-output coverage, source quotes, numeric support, qualifiers, relationship order and section attribution | v3 adversarial factuality goldens, relationship order and section attribution | Deterministic gate passes; semantic limits remain |
| CV audit history | prompt/model/profile/source CV fingerprint/evidence/validation/usage persisted | DB integration test | Complete |
| Job recovery | persisted job system state recovers unfinished work across runs | failed-tailoring retry E2E test | Complete |
| Notification idempotency | recorded job/channel delivery suppresses later digests | integration + E2E rerun tests | Durable ambiguous attempts block resend; operator reconciliation tested |
| API write security | bearer token for writes and manual trigger | API security regression tests | Complete |
| HTML/link safety | escaped dashboard/email output; unsafe URL schemes blocked | XSS regression tests | Complete |
| Security headers | CSP, frame denial, nosniff, referrer policy | API header test | Complete |
| End-to-end acceptance | mocked complete pipeline + failure injection | CI E2E harness | Automated checks pass; live acceptance pending |
| Source health telemetry | per-source persisted counts and consecutive-zero warning events | DB integration tests | Complete |
| Model usage/cost telemetry | ranking/CV tokens persisted per artifact and run; cost rates configurable | unit + DB integration assertions | Complete |
| Live provider smoke | one semantic rank + one evidence-gated CV, no DB/email side effects | explicit opt-in command | Live checks recorded in Checkpoint 5 |

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

Real-candidate smoke and ranking evaluation have run with explicit consent.
The ranking promotion gate failed (Precision@5 0.8, pairwise 0.96 versus 1.0/1.0);
model ranking and automatic specialist workflow remain disabled. Three reviewed
CV previews passed factuality while retaining the source claims unchanged.
One explicitly approved staged pilot digest was acknowledged by Gmail; inbox
receipt was confirmed by the user on 2026-10-08. Production still needs quality acceptance, off-host
backups, independent alerts, OAuth lifetime handling and a scheduling decision.
Passing CI does not authorize a merge. See [Checkpoint 5](CHECKPOINT_05.md).

## Gemini live-smoke progress

Gemini 3.1 Flash Lite passed the complete four-role **synthetic** workflow,
including a caught unsupported employer/skill claim and a successful bounded
revision (19 requests). Gemini tool-option compatibility, final-answer turn
allowance and repeated-read control were fixed and regression-tested; CI #282
passed. Two live-derived fictional CV fixtures bring the factuality dataset to
28 cases. Representative ranking/CV quality, live sources, email and target-host
acceptance remain pending. Automatic agent mode is still disabled.

## Current pilot checkpoint

[Checkpoint 5](CHECKPOINT_05.md) now includes consented real-CV evaluation and one
human-approved three-job staged digest. Mac database/restore/protected-read checks
passed. Private CVs and credentials remain untracked. Model ranking failed its
promotion gate; deterministic ranking remains configured. No scheduler or merge.


## Fresh supervised follow-up

Three current-session candidates traversed isolated persistence and deterministic
ranking. One single-writer CV passed; two were rejected and then passed a CV-only
writer/reviewer retry. No repeat scrape/rank or new email occurred. Independent
`CV_REVIEW_ENABLED` supports this configuration; missing source descriptions are
now rejected. Raw model warnings/summaries still require review, and final CV
usefulness remains a release gate. See Checkpoint 5 for preserved failures/limits.


## Saved review workflow — 2026-10-09

Pipeline delivery now defaults to `review`: immutable content snapshots are saved
for explicit approval and one-shot send. Browser UI, authenticated APIs and CLI
replace one-off preview/delivery scripts. Changed job/CV/source evidence or recipient
invalidates sending; concurrent attempts and ambiguous delivery remain guarded.
See [DIGEST_REVIEW.md](DIGEST_REVIEW.md). No new live email or model calls were made
for this implementation. CV utility, ongoing pilot observation and hosting remain.


## Observed CV differences and section emphasis — 2026-10-09

New saved previews and digest summaries describe computed source/output differences,
with an exact diff available in the review UI. Model-authored summaries, keywords
and warnings are retained only as unverified audit commentary. Existing version-1
snapshot approvals preserve their original neutral notice.

Complete sections now move by role family while retaining their wording and employer
context. The first live trial failed both cases (28 requests); unsupported rewrites
and evidence mapping errors were blocked, including one mistaken reviewer approval.
Writer v6 preserves complete source wording; workflow v3 clarifies evidence repair.
The bounded retry passed both captured engineering/product cases in 10 requests,
with all 42 source statements retained, no added/omitted passages and zero revisions.

Validation: 232 tests passed in CI for `bb410a8`; lint and fictional browser diff
preview checks passed. No email or database changes occurred in these quality trials.
This improves section emphasis, not qualification gaps or profile rewriting; human
usefulness acceptance and broader reliability remain open.
[Sanitized quality report](../../evals/reports/cv_section_emphasis_checkpoint05.json).
