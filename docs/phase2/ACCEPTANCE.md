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

Qualification triage now exposes documented mentions and gaps separately from role
relevance. It does not certify proficiency or replace matching-quality acceptance.
Evaluate extraction coverage and human usefulness before considering automatic
qualification decisions; existing ranking benchmark labels/weights are unchanged.


Consolidated-source follow-up: three regenerated CVs pass with all 56 source
statements retained after bounded provider-failure retries. A replacement digest
is pending and unsent. Remaining editorial work is a concise role-specific resume
view; full evidence inventories and skill mentions are not final fit acceptance.


## User ratings received — 2026-10-12

The ten-job editorial sample received four Keep, four Stretch and two Pass ratings.
The agreed eight-of-ten Keep target was **not met**; Stretch is not counted as Keep.
Per the bounded-pass agreement, freeze this review and proceed with manual selection
for the next supervised pilot. Four explicit selections are stored privately; four
stretch roles require separate selection, and two passed vacancies are excluded
from this batch. This does not create company-wide exclusions or alter ranking
weights, benchmark labels, resume approval, email authorization or applications.
The older pending digest is unchanged. Refresh the selected vacancies before the
next pilot. [Sanitized result](../../evals/reports/user_ratings_checkpoint05.json).


### 2026-10-12 — Feedback-tuned automatic selection and international scope

The user superseded the manual-selection fallback and requested another automatic-selection pass. Profile v2 preserves all ten exact vacancy decisions, prioritizes applied AI/AI engineering and technical product roles, and holds broader senior/staff product roles as stretch. These are provisional preference rules inferred from a small feedback set, not model training or demonstrated acceptance improvement.

Discovery now includes NYC, San Francisco, Los Angeles and London, UK, alongside existing Canadian scope. The pipeline applies a separate selection gate before CV generation regardless of ranking provider. International roles require explicit sponsorship willingness; an employer's affirmative sponsorship policy with a general per-candidate caveat is eligible but marked offered_with_caveat. Silence, hypothetical offers and conflicting or negative statements remain held. Remote alone does not establish geographic eligibility. Exact Keep ratings cannot bypass sponsorship checks. Selection decisions and exact sponsorship excerpts are recorded in pipeline events.

The fresh read-only employer-board pass captured 1,627 postings and yielded seven candidates at the existing 65-point threshold: Capco and Zafin in Toronto, plus five Anthropic applied-AI roles in London or NYC/SF. All five international candidates have a general sponsorship caveat, not guaranteed individual sponsorship. No qualifying LA result was found. Five board requests failed; coverage is incomplete. No new user acceptance score is claimed, and none of these roles was sent or applied to. The older pending digest remains unchanged.

Greenhouse discovery now decodes escaped HTML, applies its cap after title filtering and preserves full descriptions so sponsorship restrictions at the end are not dropped. Capco/Zafin boards are included. The attempted word-boundary scoring change reduced synthetic pairwise accuracy (.975 to .945833) and was reverted; original ranking metrics remain intact.

Validation: 260 local tests passed, including sponsorship negatives/conflicts, exact rating precedence, source-tail preservation and an end-to-end hold preventing CV generation/delivery. Lint and offline acceptance passed. See evals/reports/international_selection_checkpoint05.json. Private full results: .local/international-selection/REVIEW.md. Scheduler remains off, PR remains draft, and no merge is authorized. Next: exercise these selection rules in the next supervised pipeline run, broaden reliable board coverage, then complete deployment gates.


### Release-candidate native pilot passed — 2026-10-12

Native discovery (no injected job shortlist) produced 185 jobs: Greenhouse 73, Ashby 112, LinkedIn/Indeed zero under the source deadline. Automatic selection chose the four previously rated Keep vacancies. Gemini writer/reviewer checks accepted four CVs in 34 requests; all preserve source wording and reorder complete sections. A pending digest was saved in the isolated release_candidate_01 database. No email or delivery attempt occurred. The original pilot pending digest was not replaced.

A controlled replay of those same 185 rows created zero new jobs, CVs, batches, or delivery attempts and preserved the pending fingerprint. Actual pilot backup/restore matched all eight audited application/migration tables. The initial stopped discovery worker was recovered through the supported recovery path, and the retry retained lineage. Disposable operational rehearsal verified backup equality and authenticated/unauthenticated endpoint behavior. 264 local tests passed; CI passed on the adapter/deadline implementation commits.

See evals/reports/release_candidate_checkpoint05.json. Private review package: .local/release-candidate-02/REVIEW.md. This validates technical flow and honors known user selections; it is not a blind international matching evaluation or proof of CV presentation quality. Outstanding production gates are review/send authorization, production host, off-host backups/restore, independent alerts, durable OAuth, and final release/schedule approval. No further tuning cycle is required merely to repeat these completed checks.
