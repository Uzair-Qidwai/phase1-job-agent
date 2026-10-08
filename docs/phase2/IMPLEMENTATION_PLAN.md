# Phase 2 Implementation Plan

## Build Strategy

Phase 2 is implemented as incremental vertical slices. Each slice must leave the branch runnable and covered by tests.

## Workstream 1 — Foundation

Deliverables:

- validated settings module;
- .gitignore;
- CI workflow;
- lint/static-quality tooling;
- deterministic test environment;
- architecture/eval documentation.

Acceptance:

- clean checkout can install development dependencies and run tests;
- unit tests do not require real API credentials;
- CI runs automatically on pull requests.

## Workstream 2 — Stable Job Identity

Deliverables:

- source-aware URL canonicalization;
- source_job_id support;
- Indeed identity regression fix;
- canonicalization golden fixtures;
- DB migration plan for source identity.

Acceptance:

- distinct Indeed `jk` values never dedupe into one job;
- tracking parameters do not create duplicate identities;
- existing supported source URLs have deterministic canonical forms.

## Workstream 3 — Pipeline Run Ledger

Deliverables:

- pipeline_runs;
- pipeline_events;
- stage status;
- single-run lock;
- retry/resume semantics;
- structured metrics and errors.

Acceptance:

- concurrent run attempt is rejected safely;
- failed stage is persisted;
- run can resume without duplicating completed ingestion;
- run summary includes counts and durations.

## Workstream 4 — Source Adapter Layer

Deliverables:

- JobSource interface;
- LinkedIn adapter;
- Indeed adapter;
- Greenhouse adapter;
- adapter contract tests;
- source health metrics.

Acceptance:

- orchestrator has no source-specific parsing logic;
- every source passes the RawJob contract suite;
- one source failure does not erase successful results from others.

## Workstream 5 — Candidate Profile + Ranking

Deliverables:

- structured candidate profile;
- Stage 1 deterministic eligibility filters;
- RankingResult schema;
- semantic ranking service;
- explainable component scores;
- golden ranking dataset + metrics.

Acceptance:

- obvious hard mismatches are excluded before expensive ranking;
- every score has component explanation;
- ranking eval report is produced for scoring/model changes.

## Workstream 6 — CV Generation Hardening

Deliverables:

- typed TailoredCVResult;
- prompt/model version metadata;
- evidence_used field;
- evidence validator;
- CV version history;
- malformed-output retry policy.

Acceptance:

- malformed generated output cannot be persisted as a valid CV;
- unsupported material claims fail the evidence gate;
- every CV records model, prompt version, profile version, and source CV version.

## Workstream 7 — Notification + API Security

Deliverables:

- notification state table;
- exactly-once digest logic;
- authentication for mutations;
- protected pipeline trigger;
- HTML escaping;
- URL validation;
- typed UUID path parameters;
- CORS/security headers.

Acceptance:

- repeating the same run does not resend the same job notification;
- anonymous write/pipeline requests are denied;
- hostile scraped HTML renders inertly.

## Workstream 8 — End-to-End Hardening

Deliverables:

- mocked full-pipeline smoke test;
- fault injection;
- cost/latency telemetry;
- Phase 2 acceptance eval report.

Definition of done:

A scheduled run can discover, normalize, deduplicate, filter, rank, selectively tailor, and notify without duplicate work. Every important stage is auditable, failures can be diagnosed and safely retried, mutation endpoints are protected, and the critical workflow is enforced by automated tests and eval gates.

## Explicitly Deferred to V2

- automatic application submission;
- application-form browser automation;
- networking/outreach;
- large-scale cover letters;
- interview coaching;
- multi-user product architecture;
- billing;
- frontend rewrite.
