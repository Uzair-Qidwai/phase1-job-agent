# Phase 2 Architecture — Trusted Job Intelligence Core

## Objective

Phase 2 turns the Phase 1 prototype into a reliable, observable, secure job-intelligence pipeline without introducing unnecessary product/UI complexity.

The architectural goals are:

1. make every pipeline run traceable and restartable;
2. establish stable job identity and idempotent ingestion;
3. separate eligibility/ranking from expensive CV generation;
4. make ranking explainable and measurable;
5. make CV generation structured, evidence-constrained, and auditable;
6. prevent duplicate notifications and overlapping pipeline runs;
7. protect mutation and pipeline-trigger boundaries;
8. establish CI, regression tests, and eval harnesses before V2 feature work.

## System Flow

```mermaid
flowchart LR
    S[Job Sources<br/>LinkedIn / Indeed / ATS] --> A[Source Adapters]
    A --> N[Normalize + Canonicalize]
    N --> P[(PostgreSQL)]
    P --> F[Stage 1<br/>Deterministic Filters]
    F --> R[Stage 2<br/>Explainable Ranking]
    R --> G{Shortlist Gate}
    G -->|pass| C[CV Tailoring]
    G -->|fail| X[Retain for history]
    C --> V[Evidence Validation]
    V -->|valid| CV[(CV Versions)]
    V -->|invalid| E[Generation Failure / Retry]
    CV --> D[Notification Engine]
    D --> API[Protected API / Dashboard]

    O[Pipeline Orchestrator] --> A
    O --> F
    O --> R
    O --> C
    O --> D
    O --> PR[(Pipeline Runs / Events)]

    M[Observability<br/>logs / source health / cost / latency] -.-> A
    M -.-> R
    M -.-> C
    M -.-> D
```

## Component Model

```mermaid
classDiagram
    class JobSource {
      <<interface>>
      +discover(context) list~RawJob~
    }

    class LinkedInSource
    class IndeedSource
    class GreenhouseSource

    JobSource <|.. LinkedInSource
    JobSource <|.. IndeedSource
    JobSource <|.. GreenhouseSource

    class JobNormalizer {
      +normalize(raw: RawJob) CanonicalJob
      +canonicalize_url(url, source) str
      +extract_source_job_id(raw) str
    }

    class JobRepository {
      +upsert_job(job) tuple
      +get_jobs(...)
      +save_ranking(...)
      +save_cv_version(...)
      +mark_notified(...)
    }

    class EligibilityFilter {
      +evaluate(job, profile) FilterResult
    }

    class RankingService {
      +rank(job, profile) RankingResult
    }

    class CVTailoringService {
      +tailor(job, profile, master_cv) TailoredCVResult
    }

    class EvidenceValidator {
      +validate(result, master_cv, profile) ValidationResult
    }

    class NotificationService {
      +build_digest(jobs) str
      +send_digest(jobs) DeliveryResult
    }

    class PipelineOrchestrator {
      +start_run(trigger) Run
      +execute_stage(run, stage)
      +resume_run(run_id)
    }

    class CandidateProfile {
      +version
      +target_roles
      +locations
      +work_authorization
      +skills
      +constraints
    }

    PipelineOrchestrator --> JobSource
    PipelineOrchestrator --> JobRepository
    PipelineOrchestrator --> EligibilityFilter
    PipelineOrchestrator --> RankingService
    PipelineOrchestrator --> CVTailoringService
    PipelineOrchestrator --> NotificationService
    JobSource --> JobNormalizer
    RankingService --> CandidateProfile
    EligibilityFilter --> CandidateProfile
    CVTailoringService --> EvidenceValidator
```

## Pipeline State Machine

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> SCRAPING
    SCRAPING --> PERSISTING
    PERSISTING --> FILTERING
    FILTERING --> RANKING
    RANKING --> TAILORING
    TAILORING --> NOTIFYING
    NOTIFYING --> COMPLETED

    SCRAPING --> FAILED
    PERSISTING --> FAILED
    FILTERING --> FAILED
    RANKING --> FAILED
    TAILORING --> FAILED
    NOTIFYING --> FAILED

    FAILED --> RESUMING
    RESUMING --> SCRAPING
    RESUMING --> PERSISTING
    RESUMING --> FILTERING
    RESUMING --> RANKING
    RESUMING --> TAILORING
    RESUMING --> NOTIFYING
```

A run records its last completed stage. Resumption must not repeat work that has already been committed successfully.

## Core Data Contracts

### RawJob

Source-specific discovery output.

- title
- company
- location
- url
- description
- source
- source_job_id when available
- discovered_at
- source_payload metadata when useful

### CanonicalJob

Normalized internal representation.

- source
- source_job_id
- canonical_url
- title
- company
- normalized_company
- location
- description
- content_hash

Preferred identity constraint:

```text
UNIQUE(source, source_job_id)
```

For sources without a stable native ID, a deterministic fallback identity may be derived from canonical URL plus source.

### RankingResult

- total_score: 0..100
- hard_mismatch: bool
- component_scores
- explanation
- ranking_model / prompt version
- candidate_profile_version

### TailoredCVResult

- tailored_cv
- changes_made
- evidence_used
- keywords_added
- warnings
- model
- prompt_version

The generation is not considered valid until evidence validation succeeds.

## Source Adapter Rule

Browser scraping is a fallback, not the default integration strategy.

Preferred hierarchy:

1. official/public ATS endpoint or feed;
2. company careers endpoint;
3. structured aggregator endpoint;
4. DOM/browser scraping where necessary.

Every adapter emits the same RawJob contract and reports source-health metrics.

## Candidate Profile

Matching preferences must not be duplicated across hard-coded prompts.

The candidate profile is the source of truth for matching constraints and preferences. The master CV is the source of truth for claims that may appear in generated application documents.

## Ranking Architecture

Stage 1 applies deterministic rules such as location, role family, obvious seniority mismatches, work-authorization constraints, excluded companies, and other configured hard rules.

Stage 2 produces semantic fit only for candidates that survive Stage 1.

CV generation happens only after a shortlist threshold is met.

## Reliability Rules

- only one active pipeline run at a time;
- stages are idempotent;
- failed work remains retryable from persisted state; a general bounded-backoff
  policy remains a design target, not a completed application-level feature;
- external-service failures are explicit, not silently swallowed;
- each run records counts, durations, errors, and external-call cost metadata;
- persisted notification state suppresses recorded deliveries; external send
  success before the delivery record commits can still lead to a duplicate retry.

## Out of Scope for Phase 2

- automatic application submission;
- large-scale cover-letter generation;
- LinkedIn outreach/network automation;
- multi-user SaaS;
- billing/subscriptions;
- mobile application;
- frontend rewrite;
- conversational UI.


## Recovery Semantics

Failed runs retain their failed `current_stage`. A retry may reference the failed run through `retry_of_run_id`, creating an auditable lineage.

Safe restart points are deliberately conservative:

| Failed stage | Restart from | Reason |
| --- | --- | --- |
| created | scraping | no useful stage work has committed |
| scraping | scraping | discovery results may be incomplete |
| persisting | scraping | in-memory raw jobs may have been lost; dedupe makes re-ingestion safe |
| filtering | filtering | persisted `discovered` jobs reconstruct remaining work |
| ranking | filtering | partially ranked jobs have already transitioned state; remaining `discovered` jobs can be re-filtered |
| tailoring | tailoring | only `shortlisted` jobs without a successful CV remain |
| notifying | notifying | only `tailored`, undelivered jobs remain eligible |

The orchestrator never relies on local variables from the failed process when resuming after filtering. Recovery is reconstructed from PostgreSQL job state.

Two fault-injection acceptance cases enforce this behavior:

1. ranking failure → resume from filtering without another scrape;
2. notification failure → resume at notification without another scrape, ranking pass, or CV generation.

The API exposes an authenticated retry action for failed run IDs. The retry is still protected by the same database-backed single-active-run constraint as scheduled and manual execution.

## Stranded run recovery

All workers hold a PostgreSQL session execution lock alongside the durable
active-run admission constraint. Operator recovery requires confirmed shutdown
and the same execution lock, and records a stage-preserving failed transition
and audit event atomically. See [OPERATIONS.md](OPERATIONS.md) for the deployment
contract, network-partition limitation, and recovery/retry steps.
