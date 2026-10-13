# Job Agent — Phase 2

A single-user job discovery and CV preparation pipeline. It discovers jobs,
applies candidate preferences and sponsorship rules, ranks eligible roles,
validates CV evidence, and saves an exact digest for review before sending.
It does not submit job applications.

## Current status

**Release-candidate pilot passed; cloud deployment is next.**

- Development branch: `phase2-foundation`.
- [Draft PR #1](https://github.com/Uzair-Qidwai/phase1-job-agent/pull/1) remains open;
  no merge or unattended scheduler activation has been approved.
- The October 12, 2026 native pilot discovered and ranked **185 jobs**, selected
  **four**, and produced **four evidence-validated CVs** using **34 Gemini requests**.
- Replaying the same discovered rows created no duplicate jobs, CVs, batches or
  delivery attempts. Stopped-worker recovery and actual pilot backup restoration passed.
- **264 local tests passed**, along with CI on the release-candidate checkpoint.
- The pilot digest remains pending. No email was sent during this pilot.
- Cloud hosting was selected on October 13; provider selection and provisioning
  remain outstanding. The service is not deployed to production.

See [Checkpoint 5](docs/phase2/CHECKPOINT_05.md),
[acceptance evidence](docs/phase2/ACCEPTANCE.md), and the
[sanitized pilot report](evals/reports/release_candidate_checkpoint05.json).
Private CVs, credentials, database dumps and digest previews are not committed.

## Components

| Component | Implementation / current behavior |
|---|---|
| Discovery | Public Greenhouse and Ashby feeds; Playwright adapters for LinkedIn and Indeed |
| Selection | Exact vacancy feedback, preferred role families, geography and sponsorship checks |
| Ranking | Explainable deterministic baseline; model ranking remains opt-in and unpromoted |
| CV preparation | Provider-independent generation, deterministic factuality checks, optional specialist reviewer |
| Model providers | Gemini, OpenAI and Anthropic APIs; latest pilot used Gemini writer/reviewer |
| Persistence | PostgreSQL: jobs, CV versions, run history, source observations, approvals and delivery attempts |
| Scheduling | APScheduler; scheduling remains disabled pending release approval |
| Email | Gmail OAuth with send scope; saved digest approval is the default |
| Review and operations | FastAPI dashboard, review page, authenticated API and CLI |

Agent roles run inside the application; they do not require separate servers.
Provider adapters use API credentials, not a ChatGPT or other browser subscription.

## Selection and coverage

The current profile prioritizes AI engineering and technical product roles and
preserves the ten reviewed vacancies' exact Keep/Stretch/Pass decisions. Broader
senior/staff product roles are held as stretch options. These are provisional
preference rules, not a trained model or a demonstrated improvement on unseen jobs.

Search scope includes Canadian locations plus **New York, San Francisco,
Los Angeles and London, UK**. International automatic selection requires explicit
sponsorship willingness. An affirmative employer policy with a general
per-candidate caveat is recorded as `offered_with_caveat`; it does not guarantee
sponsorship for the applicant. Unknown, negative or conflicting statements remain
held. Remote alone does not establish worldwide eligibility. Keep ratings cannot
bypass these checks.

Each discovery adapter has a configurable deadline, defaulting to 180 seconds.
A failed or timed-out source cannot discard completed results from healthy
adapters. Timed-out partial results are discarded and a warning is logged.

The native pilot returned 73 Greenhouse and 112 Ashby jobs, with no LinkedIn or
Indeed results under the deadline. Ashby covers WorkOS, Cohere and MaintainX.
Two configured Greenhouse board addresses, Chainalysis and Alchemy, returned 404
in the latest diagnostic. Coverage is therefore incomplete. The four selected
pilot vacancies were previously rated Keep; this was not a blind international
matching evaluation.

## Local setup

### 1. Install the application and browser

```bash
git clone https://github.com/Uzair-Qidwai/phase1-job-agent.git
cd phase1-job-agent
git switch phase2-foundation
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
playwright install chromium
```

Linux deployments must also install Playwright's operating-system dependencies.
Cloud packaging and persistent service configuration are still to be completed.

### 2. Configure private settings

```bash
cp .env.example .env
chmod 600 .env
```

Set a real `POSTGRES_URL`, a strong `API_TOKEN`, the chosen provider's API key,
an explicit model where required, and a private `MASTER_CV_PATH`.
Do not commit `.env`, OAuth files, personal CVs or database backups.

The example environment retains generic defaults; it is not the pilot's private
configuration. For the validated workflow, configure these explicitly:

```dotenv
RANKING_MODE=deterministic
AGENT_WORKFLOW_ENABLED=false
CV_REVIEW_ENABLED=true
DIGEST_DELIVERY_MODE=review
API_REQUIRE_READ_AUTH=true
DISCOVERY_SOURCE_TIMEOUT_SECONDS=180
```

Choose `MODEL_PROVIDER=gemini`, `openai` or `anthropic` and configure the matching
key. OpenAI/Gemini require an explicit `MODEL_NAME` or per-role `AGENT_MODELS`.
Use an available model and its actual input/output prices. Missing prices mean
unknown cost; only use zero prices for a genuinely free model configuration.
Set `PIPELINE_MAX_MODEL_CALLS` and, where appropriate, `MODEL_SPEND_STOP_USD`.
The spending stop can overshoot by one in-flight response; it is not a provider
billing cap. The controlled pilot used additional request pacing; free-tier
capacity must be verified for the cloud deployment.

Keep the master evidence file private, for example under ignored `.local/`, and
point `MASTER_CV_PATH` to it. Review `data/candidate_profile.json` for preferences;
search preferences are not candidate credentials.

### 3. Prepare PostgreSQL

Create a dedicated database and application account, then run from the checkout:

```bash
python -m src.migrations
```

The ordered runner records migration filenames and checksums, locks concurrent
runners and applies pending migrations transactionally. Never edit, rename or
remove an applied migration; add the next contiguous numbered file instead.
Back up before upgrades. Rollback requires a reviewed forward migration or a
restore; SQL migrations are not bundled in the package wheel.

### 4. Configure Gmail securely

Follow [Gmail setup](docs/phase2/GMAIL_SETUP.md). Enable Gmail API, create the
appropriate OAuth client, and keep its downloaded JSON private. The local setup
helper writes the credentials without asking you to print or paste tokens:

```bash
python scripts/configure_gmail.py \
  --client-file /absolute/path/to/private/client.json \
  --sender your-personal-account@gmail.com \
  --recipient your-digest-address@example.com
```

Durable OAuth authorization is a production gate. Resolve testing-mode token
longevity and verify refresh from the deployment host before unattended operation.

### 5. Check readiness

```bash
python -m evals.preflight
```

This is an offline configuration check, not proof of live provider, database or
Gmail connectivity. Running the actual pipeline can consume model quota and
sends CV content to the configured model provider.

## Running and reviewing

Start the local API on loopback:

```bash
uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Open `/review` to inspect saved digests and CVs; `/dashboard` shows job history.
The review shell contains no private batch data. Supply the API token for its
protected requests. Keep read authentication enabled before cloud exposure.

Run a manual pipeline after configuration and migrations:

```bash
python -m src.scheduler --run-now
```

With `DIGEST_DELIVERY_MODE=review`, this saves a pending digest rather than
sending it. Approval binds the exact snapshot fingerprint. Changed content or
recipient invalidates that approval; uncertain delivery blocks blind resend.
CVs are not attached to the digest. See the
[review workflow](docs/phase2/DIGEST_REVIEW.md) for CLI commands and reconciliation.

The scheduler entry point is `python -m src.scheduler`. **Do not enable it as part
of setup yet.** Production scheduling needs explicit release approval. Its default
schedule is 08:00 America/Toronto and is configurable in the environment.

## API and operational controls

| Method | Path | Purpose |
|---|---|---|
| GET | `/jobs`, `/jobs/{id}` | Job lists and detail |
| PATCH | `/jobs/{id}/status`, `/jobs/{id}/notes` | Update tracking fields |
| GET | `/dashboard`, `/review` | Job dashboard / digest review shell |
| GET / POST | `/digests` | List / prepare review batches |
| GET | `/digests/{id}` | Exact saved snapshot |
| POST | `/digests/{id}/approve`, `/digests/{id}/send`, `/digests/{id}/cancel` | Separate approval, delivery and cancellation actions |
| POST | `/pipeline/run` | Admit one pipeline run with database locking |
| POST | `/pipeline/runs/{id}/retry` | Stage-aware retry |
| GET | `/pipeline/runs`, `/pipeline/runs/{id}` | History, counters and retry lineage |
| GET | `/sources/health`, `/deliveries` | Source observations and delivery history |

Mutation, digest and delivery endpoints require Bearer authentication. Other data
reads are protected when `API_REQUIRE_READ_AUTH=true`; the generic example defaults
to false, so set it explicitly. Operational responses omit sensitive event details.
Source zero counts are observations, not proof of upstream health.

After a stopped worker or host crash, use the
[operator recovery runbook](docs/phase2/OPERATIONS.md). Recovery requires verified
worker shutdown and refuses a live execution lock. Never unlock a run by age alone.

## Validation and limits

```bash
ruff check src tests evals
python -m evals.run_offline_eval
# Set POSTGRES_URL to a disposable test database, then:
pytest -q
```

Database tests modify/delete test records. Never point them at pilot or production
data. Use a separate test configuration; the offline evaluator needs no live model
or email calls. CI provisions its own PostgreSQL database and checks migrations,
lint, tests and offline acceptance.

The CV gate checks output evidence, qualifiers and factual claims against the
confirmed source. The latest pilot retained wording and reordered whole sections.
It does not establish polished two-page resume quality or unrestricted rewriting
accuracy. Review CVs before use. Qualification skill mentions identify potential
evidence; they do not certify proficiency or years of experience.

The four-specialist workflow is available through `AGENT_WORKFLOW_ENABLED=true`:
researcher/analyst participate in model ranking and writer/reviewer in tailoring.
`CV_REVIEW_ENABLED=true` enables writer/reviewer checks independently. Current
release settings keep model ranking unpromoted. Agents cannot send email or submit
applications; application controls retain those responsibilities.

## Cloud deployment: next work

Cloud hosting is the agreed direction. The proposed initial shape is one VM with
separate app/scheduler/database services and backups stored outside the VM.
Provider, region, budget and dashboard access method are not selected yet.

1. Choose provider, region, spending ceiling, access method and daily schedule.
2. Package a reproducible build, browser dependencies and persistent services.
3. Provision the host, private database networking, restricted access and HTTPS where needed.
4. Install secrets and private evidence files outside Git and application images.
5. Resolve Gmail OAuth longevity and verify token refresh from the cloud.
6. Consolidate pilot histories deliberately; preserve sent-job exclusions and resolve old pending batches.
7. Run one cloud-specific pipeline check for source access, quotas and CV validation.
8. Configure off-machine backups and demonstrate restoration.
9. Configure independent alerts for missed runs, failed sources, credentials and backups.
10. Review the exact digest, authorize any test send, then approve release/merge and scheduling.

The local production-readiness checks have passed within their documented scope;
cloud acceptance and operational setup remain. Initial production behavior is
**automatic selection and preparation, with approval before sending**.

Further documentation: [status](docs/phase2/STATUS.md),
[architecture](docs/phase2/ARCHITECTURE.md),
[security](docs/phase2/SECURITY.md),
[pilot deployment](docs/phase2/PILOT_DEPLOYMENT.md), and
[acceptance](docs/phase2/ACCEPTANCE.md).
