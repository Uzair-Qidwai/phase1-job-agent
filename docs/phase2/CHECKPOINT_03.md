# Checkpoint 3 — Provider-independent specialist workflow

Status: complete for offline implementation; live promotion deferred to Checkpoint 4. Branch `phase2-foundation`; PR #1 stays Draft.
The earlier recovery checkpoint is preserved in [RECOVERY_CHECKPOINT.md](RECOVERY_CHECKPOINT.md).

## Delivery slices

1. Provider boundary: Agents SDK runtime; explicit OpenAI/Anthropic/Gemini adapters;
   per-role models, token caps, timeouts, model-call limits, normalized usage and
   honest unknown-cost reporting. Remove Anthropic coupling from ranking/CV code.
2. Four specialists: researcher extracts requirements from captured source data;
   analyst assesses fit; writer tailors from candidate evidence; reviewer requests
   bounded revisions. Existing source adapters perform discovery; no arbitrary
   URL fetch tool or new external action surface is added.
3. Scheduler integration: deterministic admission/filtering and database ownership
   remain in application code. Research/analysis occur before tailoring. The
   reviewer cannot bypass deterministic CV validation. Persist sanitized role
   execution metadata and account for failed/revised calls.
4. Offline acceptance: exercise real SDK tool loops with fake models, provider
   routing, missing credentials, budgets, malformed outputs, review rejection,
   revision limits, audit persistence, retries and the full regression suite.

Each meaningful slice must pass CI before the next. Keep the new workflow opt-in
until Checkpoint 4 validates real models. Provider capability and output quality
are not proven by adapter/unit tests. No live calls or semantic promotion here.

## Exit criteria

All four roles wired into the opt-in pipeline; existing baseline remains usable;
model/provider configuration is independent per role; no agent can mutate the DB,
send mail or submit applications; deterministic factuality remains mandatory;
usage and failure metadata are auditable; automated CI is green.

Design basis: [Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk),
[agent definitions](https://developers.openai.com/api/docs/guides/agents/define-agents),
and [provider configuration](https://developers.openai.com/api/docs/guides/agents/models).

## Slice 1 local evidence

Shared SDK runtime and provider adapters implemented; legacy injected Anthropic
clients remain a compatibility/test seam. Real SDK loops with fake models verify
tools, usage, budgets, timeouts and sanitized failures. Adapter routing is tested
without live providers. Production calls use the SDK; no implicit model choice
is made when selecting OpenAI/Gemini. CI confirmation follows on the slice commit.

## Integration delivered

Provider slice `0e3e558` passed CI #262. The opt-in pipeline now runs researcher →
analyst during ranking, then writer → reviewer during tailoring, with at most the
configured number of revision cycles. Tools are read-only views of the captured
job, master CV, preferences, and deterministic draft validation. No model controls
DB writes, recovery, notifications, or application submission.

Role executions are stored as `agent_step` pipeline events, including provider,
model, prompt version, execution ID/sequence, tool names, request/token counts,
latency, completeness flags and nullable cost estimate. Raw prompts/responses are
not stored in these events. CV validation metadata stores review results and
writer/reviewer provenance. Failed and rejected model work contributes to run
usage even when no CV is saved. Existing audit JSON/event tables suffice; no new
migration or edits to applied migration files were needed.

Limits apply per job-stage execution: one budget for research/analysis and another
for writing/reviewing; retries receive a new budget. Each specialist has a turn
cap, output-token cap, and wall-clock timeout. A per-pipeline dollar cap is not
implemented; it remains Checkpoint 4 budget work. Unknown prices or missing usage
produce null step estimates and an incomplete-cost flag; numeric legacy totals
are only known subtotals. Estimates exclude cached/reasoning-specific rate tiers.

The Agents SDK and LiteLLM adapter versions are pinned. Native OpenAI Responses
and Anthropic/Gemini adapters are exercised with offline fake responses only;
real provider availability, tool/schema behavior and quality await Checkpoint 4.
No automatic provider fallback or model promotion is enabled. Default baseline
is preserved: `AGENT_WORKFLOW_ENABLED=false`, deterministic ranking.

## Green checkpoint evidence

| Slice | Commit | Passing CI |
| --- | --- | --- |
| Provider-independent runtime and milestone map | `0e3e558` | [#262](https://github.com/Uzair-Qidwai/phase1-job-agent/actions/runs/37740042696) |
| Four specialists, scheduler audit, review gates | `addbdb9` | [#264](https://github.com/Uzair-Qidwai/phase1-job-agent/actions/runs/37776823038) |

Integration CI passed 150 tests, lint, migration checks and offline acceptance
metrics. The existing deterministic benchmark remains Precision@5 1.0 and
pairwise accuracy 1.0 across 30 jobs; 22/22 CV goldens match expected outcomes.
These figures measure fixtures, not the quality of any live agent/model.

[Saved checkpoint evidence](../../evals/reports/phase2_agent_checkpoint03.json)
records the implementation commit, CI and offline results. Real SDK tool loops,
provider routing, output-schema rejection, turn/call budgets, timeouts, independent
role models, review revisions/rejection, deterministic-gate enforcement, and DB
usage/provenance persistence are covered without real provider calls.

No live model/source/email calls were made. The opt-in feature is not enabled in
production. PR #1 remains Draft and `main` is unchanged. Checkpoint 4 is planned,
not complete; see [CHECKPOINT_04.md](CHECKPOINT_04.md).
