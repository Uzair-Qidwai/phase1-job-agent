# Phase 2 acceptance review

Updated 2026-10-08. Branch `phase2-foundation`; PR #1 remains Draft.

**Disposition: one supervised staged pilot digest sent on the selected Mac host.
Real-candidate model ranking failed promotion; CV tailoring utility remains limited.
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

1. Completed: the user confirmed inbox receipt of the one approved three-job
   pilot digest on 2026-10-08. Transport and durable delivery records also passed.
2. Review ranking quality and benchmark relevance without changing labels merely
   to obtain a pass. Real-candidate model P@5 0.8/pairwise 0.96 regressed from 1.0/1.0.
   Keep automatic model ranking off.
3. Improve or accept CV tailoring utility: three actual-listing previews passed
   factuality but retained unchanged factual claims. Preserve degree-in-progress
   and missing-skill warnings; do not infer technical credentials.
4. Configure off-host backup retention, independent alerts and OAuth lifetime
   handling before unattended operation. Dedicated Mac DB, local restore and
   authenticated reads passed; no persistent service or scheduler is installed.
5. Resolve Indeed unavailability through approved access or accept reduced coverage.
6. Review the fresh bounded rehearsal and complete an unmodified target-host run
   before deciding scheduling and final PR
   approval. The completed pilot reused captured listings and reviewed CV previews;
   it did not prove unattended end-to-end operation. Main remains unmerged.

The user explicitly authorized real CV transmission to Gemini and the single pilot
email. CVs were not attached; private evidence and credentials remain untracked.
Full evidence: [Checkpoint 5](CHECKPOINT_05.md) and its sanitized reports.
See also [PILOT_DEPLOYMENT.md](PILOT_DEPLOYMENT.md) and [OPERATIONS.md](OPERATIONS.md).

Fresh rehearsal follow-up: three CV bodies now pass after one recorded failed run
and a two-job reviewer retry. No new email was sent. Model commentary may still
infer unsupported skills; private review notes flag the observed example. See
Checkpoint 5 for scope, source failures and sanitized evidence.


Saved review workflow is now implemented (2026-10-09), with review as the delivery
default and browser/API/CLI approval of exact saved content. This closes the
one-off-script workflow gap; it does not establish CV tailoring usefulness or
unattended-production readiness. See DIGEST_REVIEW.md and Checkpoint 5.


Observed-summary follow-up: new previews show actual source/output diffs and exclude
unverified model commentary. Two captured real-CV cases passed after a preserved
failed trial, retaining all 42 source statements with role-specific section order.
Human usefulness acceptance remains pending; this does not establish free-form
rewriting quality or unattended readiness. See the CV section-emphasis report.


A fresh saved-review pilot completed with three validated, source-preserving CVs
and a pending snapshot, without sending mail. Matching acceptance remains open:
high keyword scores did not establish required skill/experience coverage. Keep
manual qualification review and resolve this gap before unattended delivery.
