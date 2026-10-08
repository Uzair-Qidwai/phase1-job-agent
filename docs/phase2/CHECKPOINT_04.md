# Checkpoint 4 — Live validation, remaining features, Phase 2 exit

Status: planned; live checks remain deferred by the user. Starts after Checkpoint 3.
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
