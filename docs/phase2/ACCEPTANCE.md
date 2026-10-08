# Phase 2 acceptance review

Updated 2026-10-08. Branch `phase2-foundation`; PR #1 remains Draft.

**Disposition: implementation and bounded synthetic/local checks pass so far.
Real email, real-candidate acceptance, hosting decision and pilot remain pending.
This is not permission to merge or enable unattended operation.**

## Current evidence

- Original recovery evidence is preserved in [RECOVERY_CHECKPOINT.md](RECOVERY_CHECKPOINT.md).
- [Checkpoint 3](CHECKPOINT_03.md) delivered the provider/specialist implementation.
- [Checkpoint 4](CHECKPOINT_04.md) records offline hardening and the initial
  successful synthetic Gemini workflow, including rejection/correction of an
  invented employer/skill claim. It is not final production acceptance.
- The 30-job **fictional** software-candidate benchmark passed on Gemini 3.1 Flash
  Lite: Precision@5 1.0, pairwise accuracy 1.0 versus deterministic 1.0/0.975.
  All six explicit exclusions used zero model requests. Total: 105 requests.
  This does not validate the real candidate profile or authorize model promotion.
- Greenhouse and LinkedIn bounded live checks returned valid descriptions and
  identities. Overlapping LinkedIn search results were exercised through the
  production normalizer. Indeed returned HTTP 403 with a blocked-page title;
  it is unavailable in this environment, not accepted as healthy.
- Local deployment rehearsal applied migrations twice, restored a synthetic
  sentinel and migration ledger to a separate database, reapplied migrations,
  compared data, and exercised four protected HTTP endpoints on a temporary
  loopback server. All unauthenticated reads returned 401; authenticated reads 200.
- A simulated delivery traversed the real durable attempt/notification boundary
  in its own database. It sent no email. Automated tests cover crashes before
  and after transport acknowledgement, blocked resends and operator reconciliation.

## Implemented safeguards

HTTP admission is reserved in the database before subprocess spawning; the
execution lock remains the final worker guard. Ordered migrations enforce history
checksums and transactional application. Operational run/source reads are bounded.
Delivery ambiguity is durably recorded before transport and blocks automatic
resends. Shared call/spend limits include retries and revisions. CV validation
checks whole-output evidence, qualifiers, relationship order and section context;
a reviewer cannot override deterministic failure. These are tested mechanisms,
not guarantees of semantic truth or exactly-once external delivery.

## Remaining acceptance gates

1. The initial synthetic CV suite passed 1/3 (41 requests). After diagnosing
   unsupported rewrites and correcting review instructions, all 3/3 passed in
   25 requests, including one revision. Original failures remain recorded.
   Real-candidate evaluation and human CV approval remain pending.
2. Review the newly provided private master CV and degree status; decide the
   acceptable provider/data-use arrangement before transmitting personal evidence.
   The actual-candidate ranking benchmark has not been promoted.
3. Configure personal Gmail sender OAuth, send the single authorized test to the
   chosen recipient and confirm inbox receipt. A university recipient needs no
   OAuth consent. Resolve testing-mode token lifetime before unattended production.
4. Confirm the pilot host and its DB account, backups, monitoring/alerts and
   recovery procedure. Local disposable rehearsal does not certify a remote host.
5. Decide how to handle Indeed unavailability in the pilot; no access bypass.
6. Approve and run a small supervised pilot, review every CV/digest, then decide
   on scheduling and final PR review/merge. Neither has been started or approved.

See [PILOT_DEPLOYMENT.md](PILOT_DEPLOYMENT.md), [GMAIL_SETUP.md](GMAIL_SETUP.md),
[LIVE_TESTING.md](LIVE_TESTING.md) and [OPERATIONS.md](OPERATIONS.md).

Full current evidence and remaining gates: [Checkpoint 5](CHECKPOINT_05.md).
