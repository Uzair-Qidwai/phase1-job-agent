# Phase 2 Checkpoint 1 — Hardened Core Baseline

Date: 2026-10-08

This checkpoint freezes the current Phase 2 foundation before the next hardening slice.

## Branch / Pull Request

- Branch: `phase2-foundation`
- Base: `main`
- Pull request: #1
- PR state: Draft
- Purpose: keep Phase 2 changes reviewable and isolated from `main` until the hardening gates are satisfied

## What is in this checkpoint

### Architecture and design
- Phase 2 architecture and system flow
- component/class model
- pipeline state model
- security contract
- evaluation-harness specification
- implementation roadmap
- documented recovery semantics

### Reliability and data integrity
- source-aware job identity and canonicalization
- Indeed `jk` dedupe regression fix
- native `source_job_id` support
- canonical job identity database uniqueness
- pipeline run/event ledger
- database-backed single-active-run protection
- source-health history
- system-state lifecycle separate from application status
- notification delivery state and duplicate prevention
- stage-aware retry/recovery policy
- failed-run retry lineage via `retry_of_run_id`

### Ranking and candidate matching
- structured candidate profile
- deterministic eligibility filtering
- explainable deterministic ranking
- semantic ranking path behind an explicit mode
- ranking golden dataset
- ranking eval metrics and promotion gate
- first-class ranking history persisted per job/run

### CV quality
- typed CV generation result
- source-CV/profile/model/prompt metadata
- evidence mapping
- deterministic evidence existence checks
- numeric hallucination detection
- claim/evidence relevance checks
- CV version history

### Security
- bearer authentication for write operations
- protected pipeline trigger
- protected failed-run retry endpoint
- typed UUID API boundaries
- safe URL handling
- HTML escaping
- security headers
- validated API-token strength

### Automated quality gates
- source identity golden fixtures
- source adapter contract tests
- ranking unit/eval tests
- semantic ranking tests
- CV generation/validation tests
- API security tests
- notification safety/idempotency tests
- PostgreSQL-backed schema/run-lock tests
- migration repeatability check
- mocked end-to-end pipeline test
- fault injection for ranking recovery
- fault injection for notification recovery

## Recovery behavior frozen at this checkpoint

| Failed stage | Safe restart point |
| --- | --- |
| created | scraping |
| scraping | scraping |
| persisting | scraping |
| filtering | filtering |
| ranking | filtering |
| tailoring | tailoring |
| notifying | notifying |

Recovery after filtering is reconstructed from persisted PostgreSQL job state rather than failed-process memory.

## Remaining hardening before Phase 2 exit

1. Verify CI remains green on this checkpoint head.
2. Harden simultaneous HTTP trigger admission so losing requests do not unnecessarily spawn child processes.
3. Decide whether to introduce a formal migration-version runner or retain ordered SQL migrations for this project size.
4. Add operational read endpoints for pipeline/source-health history.
5. Continue strengthening non-numeric CV claim factuality/evidence coverage.
6. Review all Phase 2 acceptance criteria and explicitly accept or close remaining technical debt.

## Merge policy

Do not merge this PR merely because the code is functional.

Move Draft PR #1 to ready-for-review only when:
- CI is green;
- migrations are repeatable;
- all deterministic eval gates pass;
- no known critical correctness/security issue remains;
- remaining technical debt is documented and consciously accepted.

This checkpoint is not V2 product scope. Automatic applications, browser form automation, outreach, multi-user SaaS, billing, and frontend redesign remain deferred.
