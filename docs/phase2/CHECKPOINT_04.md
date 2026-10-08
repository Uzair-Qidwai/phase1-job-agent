# Checkpoint 4 — Live validation, remaining features, Phase 2 exit

Status: offline hardening and live-test preparation implemented; live acceptance
is in progress. Synthetic Gemini validation has passed; representative quality
and deployment gates remain pending. See [live-test handoff](LIVE_TESTING.md).
Branch remains `phase2-foundation`; PR #1 remains Draft until explicit exit review.

## Ordered work

1. Configure selected provider credentials and explicit per-role models/pricing.
   Perform limited smoke calls with tools and typed outputs; capture provider,
   model, prompt, usage, latency and cost-estimate provenance. Verify each provider
   actually selected for deployment; do not claim untested-provider compatibility.
2. Run the 30-job live ranking comparison and representative CV writer/reviewer
   cases. Measure relevance, evidence coverage, false rejections, revision rates,
   latency and cost. Promote models only on recorded results; retain deterministic
   ranking until its promotion gate passes.
3. Validate live source adapters with a bounded discovery run, reviewing missing
   fields, duplicate identities and source-health observations. Expand research
   tools only if this demonstrates a concrete missing capability.
4. Close the external-send crash window operationally: design/persist delivery
   attempts with an explicit ambiguous state and a reconciliation path; inject
   crashes around send/record boundaries. Do not promise exactly-once external
   delivery without provider-level support. Actual test emails require explicit
   recipient/send authorization; dry-run delivery first.
5. Review/fix remaining runtime needs: malformed-output/provider failure retry
   policy with bounded attempts/backoff, meaningful cost/budget controls, section
   context and relationship checks for CV review, and run-level failure reporting.
6. Deployment rehearsal: migration from existing DB, controlled schedule, worker
   termination/recovery, connection-pooling assumptions, secrets, private-network
   read policy, and rollback. Back up real data before migration rehearsal.
7. Produce final acceptance report linking automated and live evidence. Document
   explicitly accepted limitations and unresolved blockers. Ready-for-review and
   merge remain separate user decisions; never auto-merge.

## Exclusions

No automatic job applications, networking/outreach, billing, multi-user SaaS or
frontend rewrite. Checkpoint 4 closes Phase 2 scope; it does not silently add V2.

## Completion gate

Green CI on the final head; selected live-provider/source tests pass; delivery
ambiguity has a tested reconciliation procedure or an explicitly accepted limit;
CV outputs remain subject to human review; deployment/recovery is rehearsed;
remaining limitations are consciously accepted. Credentials or live checks left
pending mean this checkpoint is incomplete, even if offline CI passes.

## Offline implementation progress

- Delivery attempts are committed before transport; an uncertain send blocks
  automatic resend. Stable Message-ID assists investigation, not deduplication.
  Resolving `sent` records all notifications atomically; resolving `not-sent`
  permits a later retry. Stop workers before reconciliation.
- Use `python -m src.delivery list` and `python -m src.delivery reconcile UUID
  --outcome sent|not-sent --reason 'Evidence recorded here'
  --confirm-workers-stopped`. If evidence is inconclusive, leave it unresolved.
- Tailoring failures now fail the run at the tailoring restart point after
  delivering successful jobs. Rejected CVs remain shortlisted and unsent.
- Local full suite: 154 tests pass, including send/record crash boundaries,
  reconciliation exclusion, and stage-aware retries. Live sends remain deferred.
- Runtime controls now share `PIPELINE_MAX_MODEL_CALLS` across jobs and stages.
  Tool loops and transient retries consume the same limit; per-specialist limits
  still apply. Input payload bytes and output tokens are bounded.
- Only 429/5xx errors receive bounded exponential backoff. Timeouts, malformed
  output and authentication/configuration failures do not automatically retry.
  They retain stage-aware recovery. A configured `MODEL_SPEND_STOP_USD` requires
  explicit prices and stops on unknown usage; it is a spending stop threshold,
  potentially overshooting by the last response, not a guaranteed invoice cap.
- Delivery slice CI #268 passed on `b74b960`.
- Runtime slice CI #270 passed on `561e3ab`.
- CV validator/prompt v3 preserves factual term order, structured section/role
  attribution and major source sections. Four new gold cases cover reversed
  relationships, employer swaps, intact structure and omitted sections. Neutral
  headings may be added to otherwise unstructured excerpts. This conservative
  lexical gate is not semantic entailment; live false-rejection review remains.

- CV slice CI #272 passed on `d1d49d0` (166 tests, 26 CV gold cases).
- Live-test tools now require explicit invocation and preserve private reports;
  model evaluation budgets cover the entire run. Offline preflight, synthetic
  delivery preview, optional read authentication and legacy upgrade rehearsal
  are included. Local backup/restore succeeded on disposable PostgreSQL 16 data.
- Target-host deployment, real provider/source/delivery checks and final human
  acceptance remain pending; this is live-ready preparation, not Phase 2 exit.

## Offline readiness evidence

Implementation commit `1b789ce` passed [CI #274](https://github.com/Uzair-Qidwai/phase1-job-agent/actions/runs/37802434424):
**175 tests**, lint, migration checks and deterministic evaluation. Offline metrics
remain Precision@5 1.0 and pairwise accuracy 1.0 across 30 ranking fixtures; all
26 CV gold cases match expected outcomes. Machine-readable evidence is in
`evals/reports/phase2_checkpoint04_offline.json`. Live acceptance remains pending.

## Gemini synthetic live testing

A user-confirmed free-tier project authenticated successfully. Gemini 2.5 Flash
returned an explicit new-user restriction despite appearing in the model list.
Gemini 3.8 Flash and 3.5 Flash Lite intermittently returned 503; a sanitized
provider diagnostic explicitly attributed this to high demand. 3.5 Flash Lite
passed basic typed output, native function calling, and an SDK tool round trip
with bounded backoff. No personal CV/profile, DB writes or email was involved.

The four-specialist smoke exposed a LiteLLM/Gemini incompatibility:
`parallel_tool_calls=False` is rejected when multiple tools are declared. The
runtime now omits that option for Gemini multi-tool agents; all exposed tools
remain read-only and request/turn limits still apply. Other providers and Gemini
single-tool requests retain the previous setting. Four regression cases cover
these branches. Full workflow live acceptance remains pending rerun.

Compatibility fix `e284e2f` passed CI #278 (179 tests). The next synthetic trial
completed research, ranking and writing, but the reviewer consumed all four
turns reading its four tools. Default turn allowance is now six so sequential
reads can be followed by a final answer; request caps, timeouts and revision
limits remain enforced. A regression test exercises four reads plus final output.
This tuning follows observed tool behavior, not a relaxation of evidence checks.

Turn allowance `021e28a` passed CI #280 (180 tests). A subsequent 3.5 Flash Lite
trial was interrupted by provider overload; 3.1 Flash Lite instead repeated
unchanged evidence reads. Gemini now receives `tool_choice=none` once every
available immutable evidence tool has been read, requiring synthesis on the
next request. Generic tools and other providers retain their existing behavior.
This does not waive validation or increase the request budget.

## First complete synthetic live pass

Gemini **3.1 Flash Lite** completed researcher → analyst → writer → reviewer,
including one writer/reviewer revision, in **19 requests** (cap 20), using a fully
fictional CV/profile/job. Input tokens: 16,451; output tokens: 1,289. The writer
initially asserted PostgreSQL usage under an employer where the source only
listed it as a skill. The deterministic gate and reviewer rejected that linkage;
the revision removed it and passed all checks. Both drafts are now regression
fixtures, bringing the CV golden dataset to 28 cases.

The implementation at `75441c3` passed CI #282 (181 tests before the two new
fixtures). Live evidence: `evals/reports/gemini_synthetic_checkpoint04.json`.
3.5 Flash Lite passed simpler tests but was intermittently overloaded; it is not
claimed fully validated. The local test model is now 3.1 Flash Lite. Automatic
agent workflow remains disabled; no personal data, email or pipeline DB writes
were involved. A single synthetic pass is not ranking promotion, representative
quality acceptance, or proof of production reliability.
