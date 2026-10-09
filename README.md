# Phase 1 — Job Search & CV Agent

Collects jobs from configured sources → ranks and prepares evidence-constrained CVs → tracks history in PostgreSQL → saves a digest for review and explicit approval → sends the approved email. Providers include Gemini, OpenAI and Anthropic.

---

## Stack

| Component | Tool |
|-----------|------|
| CV tailoring | Claude API (`claude-sonnet-4-5`) |
| Job scraping | Playwright + BeautifulSoup + httpx |
| Database | PostgreSQL |
| Scheduling | APScheduler |
| Email digest | Gmail API (OAuth2) |
| Dashboard | FastAPI + HTML |

---

## Setup

### 1. Clone & install

```bash
git clone <your-repo>
cd phase1-job-agent

# Create venv and install (uv recommended)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Install Playwright browser
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, POSTGRES_URL, Gmail credentials
```

### 3. Create the database

```bash
python -m src.migrations
```

### 4. Gmail OAuth setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → enable Gmail API
3. Create OAuth credentials (Desktop app)
4. Run once to get tokens:

```python
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json", scopes=["https://www.googleapis.com/auth/gmail.send"]
)
creds = flow.run_local_server(port=0)
print("REFRESH_TOKEN:", creds.refresh_token)
```

5. Paste the refresh token into `.env`

### 5. Update master CV

Edit `data/master_cv.md` with your actual experience before running.

---

## Running

### Start dashboard + API

```bash
uvicorn src.api:app --reload --port 8000
# → http://localhost:8000/dashboard
```

### Run full pipeline once (manual trigger)

```bash
python -m src.scheduler --run-now
```

### Start daily scheduler (8 AM Toronto time)

```bash
python -m src.scheduler
```

### Run tests

```bash
pytest tests/ -v
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/jobs` | List jobs (`?status=new&min_score=0.6`) |
| `GET` | `/jobs/{id}` | Job detail + tailored CV |
| `PATCH` | `/jobs/{id}/status` | Update status `{"status":"applied"}` |
| `PATCH` | `/jobs/{id}/notes` | Add notes `{"notes":"..."}` |
| `GET` | `/dashboard` | HTML dashboard |
| `POST` | `/pipeline/run` | Trigger pipeline now |

---

## Validation Checklist

- [ ] Scraper returns 10+ jobs on first run without errors
- [ ] CV tailor produces meaningfully different output per job description
- [ ] No duplicate jobs inserted on second run
- [ ] Daily digest email arrives with correct jobs
- [ ] Dashboard shows all jobs, status updates persist
- [ ] Scheduler runs without manual intervention


### Schema version discipline

From the repository checkout, run `python -m src.migrations` before starting the
API or scheduler. The runner adopts existing installations by replaying the
unchanged, idempotent 001/002 files, then records filenames and SHA-256 hashes in
`schema_migrations`. It locks concurrent runners and applies all pending SQL and
version rows in one transaction. Errors roll back the batch; fix the pending
migration and rerun. Applied files must never be edited, removed, or renamed.
Add the next contiguous numbered SQL file for schema changes. Do not put explicit
transaction control or nontransactional operations such as `CREATE INDEX
CONCURRENTLY` in these files. Back up deployed data before upgrades. This small
runner intentionally has no downgrade framework; rollback needs a reviewed
forward migration or a database restore. Run from a source checkout (SQL files
are not bundled in the package wheel).

### Operational reads

- `GET /pipeline/runs?status=failed&limit=100&offset=0`: newest runs first.
- `GET /pipeline/runs/{uuid}`: run state, counters, costs, and retry lineage.
- `GET /sources/health?source=indeed&limit=100&offset=0`: source observations.

These follow the existing unauthenticated read policy; deploy on a private
network. Run responses omit exception text, metadata, and event payloads.
Limits are 1–500 and offsets 0–100000; UUIDs and status filters are validated.
Missing run IDs return 404, empty history returns `[]`. Ordering uses timestamp
then ID; offset pages may shift as new runs arrive. Source zero counts describe
observations, not proof that an upstream service is healthy. HTTP trigger and
retry responses now include the admitted `run_id` for polling.

### CV evidence gate

The v2 gate checks all output statements, including factual headings, against the
master CV. Prefer copying/reordering complete statements. Rewrites need an exact
full-output claim and a complete source quote; all factual terms must be supported
within one quoted statement, retaining negation and qualifiers such as expected,
applicant, and assisted. Search preferences in the candidate profile are not
credentials. Failed coverage blocks generation and reports unsupported claims.
This conservative lexical check can reject valid paraphrases and cannot prove
semantic relationships or section context. Review generated CVs before use.
See `docs/phase2/CHECKPOINT_02.md` for test coverage and remaining limitations.

### Stranded pipeline runs

Use the [operator recovery runbook](docs/phase2/OPERATIONS.md) after a worker or
host crash. Recovery requires verified worker shutdown and refuses a live
execution lock; it records failure without retrying or sending email. Never
unlock by age alone. See [Phase 2 acceptance](docs/phase2/ACCEPTANCE.md) for the
current validation evidence and pending live checks.


### Checkpoint 3: specialist agents and provider choice

The default stays deterministic ranking plus validated CV generation. The new
four-specialist workflow is opt-in pending live validation:

```dotenv
AGENT_WORKFLOW_ENABLED=true
MODEL_PROVIDER=openai
MODEL_NAME=your-explicit-model-id
OPENAI_API_KEY=your-local-secret
```

Use `MODEL_PROVIDER=anthropic` with `ANTHROPIC_API_KEY`, or `MODEL_PROVIDER=gemini`
with `GEMINI_API_KEY`, to select those adapters. Keep model names unprefixed.
OpenAI/Gemini model names must be explicit; Anthropic preserves the existing
`RANKING_MODEL` fallback. This uses provider APIs, not a ChatGPT browser session.

Per-role overrides go in the JSON `AGENT_MODELS` setting, e.g. entries named
`researcher`, `analyst`, `writer`, and `reviewer`, each containing `provider`,
`model`, optional `max_output_tokens`, and optional `input_cost_per_mtok` /
`output_cost_per_mtok`. Prices must match the selected model. Missing prices are
reported as unknown, not free; numeric database totals contain known subtotals.
Global `MODEL_INPUT_COST_PER_MTOK` and `MODEL_OUTPUT_COST_PER_MTOK` apply only to
the global model configuration. Explicit role overrides have their own prices.

With the feature enabled, researcher/analyst replace the ranking model path;
writer/reviewer replace single-call tailoring. Research uses source descriptions
captured by existing adapters. Read-only tools expose that data, master CV and
search preferences. The reviewer can request at most `AGENT_MAX_REVISIONS`
rewrites and cannot override deterministic validation. Agents cannot send mail,
write to the database, or submit applications. The scheduler retains those duties.

`AGENT_MAX_MODEL_CALLS` limits each job-stage execution (ranking or tailoring),
`AGENT_MAX_TURNS` limits each specialist, and `AGENT_TIMEOUT_SECONDS` bounds each
specialist run. Output caps default to 1200 for research/analysis, 4096 for writing,
and 1800 for review, unless overridden per role. SDK/provider automatic retries
are disabled; existing persisted-state retries remain available. Production SDK
tracing exports are disabled; sanitized execution metadata is stored locally in
pipeline events. No live-provider compatibility claim is made before Checkpoint 4.

See [Checkpoint 3](docs/phase2/CHECKPOINT_03.md) and
[Checkpoint 4](docs/phase2/CHECKPOINT_04.md) for delivery and acceptance gates.

Phase 2 live-test preparation and remaining acceptance gates: [Checkpoint 4 live-test handoff](docs/phase2/LIVE_TESTING.md).


## Saved digest approval

Pipeline runs now default to saving an unsent review batch. Open `/review` to
inspect the exact email and CVs, approve the batch, then send it once. No email is
sent merely by running the pipeline. Apply migration 004 before upgrading.
See [the review workflow](docs/phase2/DIGEST_REVIEW.md) for browser/CLI usage,
configuration, authentication and uncertain-delivery recovery.
