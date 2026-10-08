# Checkpoint 3 — Provider-independent specialist workflow

Status: implementation in progress. Branch `phase2-foundation`; PR #1 stays Draft.
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
