# Current Job Agent Flowchart

Updated October 13, 2026. This describes the validated review-mode workflow on
`phase2-foundation`. Cloud hosting is planned; the scheduler remains disabled.

## Job discovery through approved delivery

```mermaid
flowchart TD
    START[Manual or authenticated HTTP trigger] --> LOCK{Database admission and execution lock}
    SCHEDULE[Daily schedule - not enabled yet] -.-> LOCK
    LOCK -->|Already running| BUSY[Reject overlapping run]
    LOCK -->|Admitted| RUN[Create run record]
    RUN --> SOURCES[Discover from Greenhouse, Ashby, LinkedIn and Indeed]
    SOURCES --> DEADLINE[Independent source deadlines and failure isolation]
    DEADLINE --> NORMALIZE[Validate records and normalize job identities]
    NORMALIZE --> STORE[(Persist new jobs in PostgreSQL)]
    STORE --> FILTER{Explicit eligibility filters}
    FILTER -->|Excluded| HISTORY[Retain job and decision history]
    FILTER -->|Eligible| RANK[Deterministic relevance ranking]
    RANK --> EVIDENCE[Assess qualification evidence and record gaps]
    EVIDENCE --> SELECT{Automatic-selection policy and score threshold}
    PROFILE[Candidate preferences and exact vacancy ratings] -.-> SELECT
    SPONSOR[International roles require sponsorship evidence] -.-> SELECT
    SELECT -->|Stretch, Pass, unknown eligibility or low score| HISTORY
    SELECT -->|Selected| CV[CV writer and optional reviewer with bounded revisions]
    MASTER[Private confirmed CV evidence] -.-> CV
    LIMITS[Model request, timeout and spending limits] -.-> CV
    CV --> VALID{Deterministic factuality and evidence checks pass?}
    VALID -->|No| RETRY[Record failure and retain job for tailoring retry]
    VALID -->|Yes| VERSIONS[(Save validated CV version)]
    VERSIONS --> PENDING[Prepare pending digest snapshot]
    PENDING --> HUMAN[Review exact email, job details and CVs]
    HUMAN -->|Cancel| CANCEL[Cancel batch without sending]
    HUMAN -->|Approve| APPROVED[Bind approval to snapshot fingerprint]
    APPROVED --> SEND[Explicit send action]
    SEND --> CHECK{Snapshot unchanged and delivery admission allowed?}
    CHECK -->|No| HOLD[Block sending; review or reconcile]
    CHECK -->|Yes| ATTEMPT[(Persist delivery attempt before contacting Gmail)]
    ATTEMPT --> GMAIL[Gmail API sends digest without CV attachments]
    GMAIL -->|Confirmed success| SENT[(Record sent notifications and delivery history)]
    GMAIL -->|Uncertain outcome| HOLD
    SENT --> DEDUPE[Exclude previously sent jobs from later digests]

    RUN -.-> AUDIT[(Run events, source observations and usage history)]
    SELECT -.-> AUDIT
    CV -.-> AUDIT
    ATTEMPT -.-> AUDIT
    AUDIT --> OPS[Authenticated operational API and review interface]
```

- Exact Keep decisions cannot bypass geography or sponsorship checks. An employer's
  affirmative sponsorship policy with a general candidate caveat can qualify, but
  is not a guarantee of individual sponsorship. Unknown or conflicting evidence is held.
- Qualification mentions and relevance scores do not certify proficiency or experience.
- The latest pilot enabled the writer/reviewer while keeping ranking deterministic.
  The optional researcher/analyst model-ranking workflow remains unpromoted.
- The reviewer cannot override deterministic evidence validation. Current validated
  CV output retains source wording and reorders complete sections.
- A run with some failed CV jobs can save a batch for successful jobs while recording
  the overall run as failed for tailoring recovery. Existing open batches are reused;
  a repeated run does not automatically replace or send them.
- Approval and sending are separate actions. An uncertain send must be reconciled
  before any retry; confirmed non-delivery requires renewed approval.
- Explicit automatic delivery exists as an opt-in configuration, but is outside this
  release workflow. Neither agents nor this pipeline submit job applications.

## Recovery flow

```mermaid
flowchart LR
    FAILURE[Stage failure] --> FAILED[Persist failed stage and retry lineage]
    CRASH[Stopped worker leaves an active run] --> VERIFY{Workers stopped and execution lock free?}
    VERIFY -->|No| REFUSE[Refuse recovery]
    VERIFY -->|Yes| RECOVER[Record abandoned-run recovery]
    RECOVER --> FAILED
    FAILED --> RETRY[Explicit protected retry]
    RETRY --> STAGE{Safe restart stage}
    STAGE -->|Discovery or persistence failed| DISCOVER[Rediscover with identity deduplication]
    STAGE -->|Filtering or ranking failed| FILTER[Resume from filtering using saved jobs]
    STAGE -->|CV generation failed| CV[Retry shortlisted CV jobs]
    STAGE -->|Notification preparation failed| NOTIFY[Resume notification preparation]
    NOTIFY --> GUARD[Existing batch and delivery-attempt safeguards still apply]
```

Recovery does not unlock a run merely because it is old. Delivery reconciliation
is separate from pipeline retry; retrying a pipeline must not bypass uncertain-send protection.

## Proposed cloud layout — not deployed

```mermaid
flowchart LR
    USER[User] --> ACCESS[Private access or authenticated HTTPS - choice pending]
    subgraph VM[Proposed cloud VM]
        API[Review dashboard and API]
        WORKER[Pipeline worker]
        TIMER[Scheduler - enabled only at release]
        DB[(Persistent PostgreSQL)]
        FILES[Private evidence files and protected credentials]
        ACCESS --> API
        API --> WORKER
        TIMER --> WORKER
        WORKER --> DB
        API --> DB
        FILES -.-> WORKER
    end
    WORKER --> BOARDS[Public job sources]
    WORKER --> GEMINI[Configured model API - Gemini in latest pilot]
    API --> GMAIL[Gmail API after approval and send action]
    DB -.-> BACKUP[Separate backup storage - to configure]
    MONITOR[Independent monitor and alerts - to configure] -.-> API
    WORKER -.-> MONITOR
```

Provider, region, budget and access method are pending. Cloud setup still requires
reproducible packaging, durable Gmail authorization, deliberate data migration,
off-machine backup/restore, independent alerts and a cloud acceptance run.
The agent roles share the application runtime; no separate agent servers are required.

## Evidence at the current checkpoint

| Check | Observed result |
|---|---|
| Native discovery | 185 jobs: 73 Greenhouse, 112 Ashby; LinkedIn/Indeed returned zero under the deadline |
| Automatic selection | Four previously user-rated Keep vacancies |
| Live CV checks | Four accepted CVs, 34 Gemini requests |
| Digest | Saved pending; no email or delivery attempt created |
| Replay of the same discovered rows | No duplicate jobs, CVs, batches or delivery attempts |
| Recovery and backup | Stopped-worker recovery and actual local pilot restore passed |
| Validation | 264 local tests and checkpoint CI passed |

This is technical workflow evidence, not a blind international relevance test,
a guarantee of source coverage, or proof of production deployment.
See [Checkpoint 5](CHECKPOINT_05.md), [operations](OPERATIONS.md),
[digest review](DIGEST_REVIEW.md) and the
[sanitized pilot report](../../evals/reports/release_candidate_checkpoint05.json).
