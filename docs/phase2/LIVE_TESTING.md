# Checkpoint 4 — live-test handoff

Offline preparation is complete. A synthetic Gemini four-role smoke has passed;
representative quality and production acceptance are **pending**.
Keep PR #1 draft and scheduling disabled until the staged checks below succeed.
All commands run from the repository root with its virtual environment active.
Private reports belong in `.local/` (ignored by Git), never in committed fixtures.

## 1. Configure and inspect without making calls

Choose the provider/models for each deployed role. Configure their keys locally
in `.env` or the runtime secret store; do not paste credentials into reports/chat.
Use `AGENT_MODELS` for mixed providers or `MODEL_PROVIDER` + `MODEL_NAME` for a
single provider. Each selected model needs explicit input/output cost rates.
Do not infer current prices from the historical Anthropic default.

For the four-role trial set `AGENT_WORKFLOW_ENABLED=true`. Start with
`PIPELINE_MAX_MODEL_CALLS=12` and `MODEL_SPEND_STOP_USD=1` (adjust intentionally
for chosen model prices). Keep `RANKING_MODE=deterministic` for normal operation;
the agent workflow itself uses the analyst when enabled. Do not enable that
workflow in the scheduled deployment before the ranking promotion gate passes.
Model calls, tool loops, retries and revisions all consume the shared call cap.
The spending threshold may overshoot by the final response; use provider billing
controls for an actual hard spending limit. Unknown usage stops guarded calls.

```bash
python -m evals.preflight
python -m evals.delivery_preview --output .local/digest-preview.html
```

Preflight makes no provider, source, database or Gmail requests. A nonzero exit
lists missing model setup. It does not validate the credentials remotely.
Review `data/master_cv.md` before transmitting it: verify dates, expected degrees,
current roles and placeholder contact details. That source remains the factual
boundary. The preview is synthetic and sends nothing.

## 2. Model smoke, then ranking/CV evaluation

Each command explicitly permits paid calls but never sends email or writes DB
state. Use a new output path for every run. Reports retain sanitized failure and
usage metadata even when a provider fails. CV reports contain personal drafts.

```bash
python -m evals.live_provider_smoke --allow-live --output .local/model-smoke-01.json
```

Run this for the actual configured role/provider combinations. Success for one
provider is not evidence for the other providers. Inspect tool/typed-output
behavior, latency, usage completeness and configured price attribution.

After smoke passes, intentionally raise the request/spend limits for the 30-job
comparison (e.g. 100 calls, a personally chosen spending threshold). The cap is
shared across the entire evaluation, not reset per job.

```bash
python -m evals.run_semantic_eval --allow-live --output .local/ranking-01.json
python -m evals.run_cv_eval --allow-live --output .local/cv-review-01.json
```

Ranking must not regress against deterministic Precision@5 or pairwise accuracy.
Review all three CV cases for factual support, employer/credential attribution,
completeness and relevance. Record false rejections and revision counts as well
as latency/cost. Generation success is **not** human acceptance. The v3 lexical
validator deliberately rejects some legitimate paraphrases and cannot prove
semantic truth; no CV is automatically submitted anywhere.

## 3. Bounded source and delivery checks

These source commands fetch real source data; they make no model calls, DB writes
or sends. Each is capped at 120 seconds and 1–3 entries per query/board before
adapter filtering. A zero-result run is inconclusive/failing, not a healthy pass.

```bash
python -m evals.source_smoke --allow-live --source greenhouse --limit 2 --output .local/greenhouse-01.json
python -m evals.source_smoke --allow-live --source linkedin --limit 2 --output .local/linkedin-01.json
python -m evals.source_smoke --allow-live --source indeed --limit 2 --output .local/indeed-01.json
```

Inspect validity, duplicate identities, missing descriptions and the returned
samples. Browser adapters require the Playwright Chromium runtime. Do not bypass
source access controls if an adapter is blocked; record the limitation.

A real Gmail test remains a separate action requiring an explicitly authorized
recipient/send. First inspect the local digest preview. For a controlled pipeline
trial, use an isolated database and known test jobs; ordinary pipeline execution
may scrape, call models and email all eligible backlog, so it is not a smoke
command. Follow the delivery reconciliation procedure in `OPERATIONS.md` if the
send outcome is uncertain. Never automatically resolve uncertainty as not sent.

## 4. Deployment rehearsal and exit

- Stop scheduler, API triggers and all workers. Back up the real deployment DB
  with `pg_dump -Fc` and test restoration to a **new** DB before migrating it.
  Never restore over the running database as a test.
- Run `python -m src.migrations` twice against the restored DB; the second must
  apply nothing. Compare retained job/CV/run data and migration checksums.
  Use one application in the public schema per DB; historical foundation SQL
  was not designed for multiple application schemas in the same database.
- Use direct PostgreSQL or session pooling, not transaction pooling. Worker
  execution locks require a persistent session. Verify the extra lock connection
  fits connection capacity. Restrict database/network access and protect secrets.
- Serve on loopback/private networking. Set `API_REQUIRE_READ_AUTH=true` before
  sharing access; job/run/source/dashboard GETs then require the bearer header.
  `/deliveries` always requires auth and excludes resolution reasons/job IDs.
  A browser dashboard behind read auth needs a trusted authenticated proxy/header
  mechanism; never put the token in a URL. Do not expose the development server.
- Confirm configured timezone/hour/minute with scheduling initially stopped.
  Perform one controlled run, verify counts/recovery and only then enable one
  scheduler instance. Existing tests cover concurrent triggers and actual worker
  process death; repeat the operator stop/recover procedure on the target host.
- Roll back by stopping workers, restoring the verified backup to a separate DB,
  and switching the matching application revision/configuration to it. Do not
  edit applied migration files or run an older sender against unresolved attempts.
  Preserve the failed DB and delivery evidence for reconciliation first.
- Record live results, accepted limitations, target-host rehearsal and final CI
  in `ACCEPTANCE.md`. Checkpoint 4 remains incomplete until these pass. Review and
  merge are explicit subsequent user decisions.

## Offline evidence already obtained

- CI #268: delivery ambiguity/reconciliation and partial-run failure reporting.
- CI #270: shared request budget, spending stop guard and bounded transient retry.
- CI #272: CV section/relationship validation v3 and 26 factuality gold cases.
- Local PostgreSQL 16 custom-format backup restored into a separate disposable DB;
  the migration runner reported no pending migrations on the restored copy.
- Full legacy-schema upgrade is tested in its own disposable database, retaining
  an existing job and applying the ordered migration ledger twice.
- Preflight reports missing credentials/prices/spend threshold as expected.
  No live model calls, source fetches or real email sends were made for preparation.

## Gemini free-tier trial findings

Gemini 3.1 Flash Lite passed a fictional four-role case in 19 requests, including
one correction of unsupported CV content. The trial paced requests at least five
seconds apart, allowed six turns per role and capped the whole test at 20 model
requests. Snapshot tools were read-only. Once every snapshot was read, Gemini
was required to return a final answer instead of repeating reads.

The user's dashboard confirmed Free tier. Zero prices described that tier only;
they are not a paid-plan cost estimate. The isolated synthetic trial used request
caps rather than the monetary stop guard so transient failures with unknown
usage could receive bounded retries. Regular production spending-guard behavior
remains unchanged. Do not copy free-tier prices into a billing-enabled project.

The normal live evaluators load the real master CV/profile. Do **not** run them
for further free-tier tests unless personal-data use has been explicitly chosen.
The successful synthetic trial is not permission to transmit the personal CV.

## Separate fictional quality benchmark

The following evaluator uses only `evals/fixtures/synthetic_quality.json`. It
patches every master-CV/profile loader in the exercised paths, paces Gemini calls
five seconds apart, preserves per-case failures, and enforces a shared request
cap. It requires explicitly configured zero free-tier prices; it is not a paid
cost-control tool. Use one evaluator at a time so pacing remains meaningful.

```bash
python -m evals.synthetic_quality --allow-live --phase ranking --max-calls 160 --output .local/synthetic-ranking-NEW.json
python -m evals.synthetic_quality --allow-live --phase cv --max-calls 60 --output .local/synthetic-cv-NEW.json
```

This fixture's labels describe a fictional software candidate and cannot promote
the actual candidate benchmark. Private personal evidence can be configured via
`MASTER_CV_PATH` without committing it. Normal live evaluators will transmit that
configured CV: obtain the personal-data-use decision before invoking them.

Source smoke now reports raw duplicate counts and verifies the same normalized
output used by production; overlapping search results are not themselves a
failure when deduplication succeeds. Empty or invalid results still fail.

For the local deployment and one-shot delivery rehearsal, see
[PILOT_DEPLOYMENT.md](PILOT_DEPLOYMENT.md) and [GMAIL_SETUP.md](GMAIL_SETUP.md).


### Independent CV review

Set `CV_REVIEW_ENABLED=true` with `AGENT_WORKFLOW_ENABLED=false` and
`RANKING_MODE=deterministic` to use the writer/reviewer correction loop without
promoting model ranking. The default is false; enabling the full agent workflow
still selects all four roles. Preflight and CV evaluations include the reviewer
when either control selects it. Model warnings and change summaries remain subject
to human review; deterministic CV-body checks do not establish their correctness.
This flag does not suppress email or create an approval queue: supervised tests
must separately isolate/intercept delivery until explicitly authorized.
