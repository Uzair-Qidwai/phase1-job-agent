# Checkpoint 5 — pre-pilot review

Date: 2026-10-08. Branch: `phase2-foundation`. PR #1 remains Draft.

**Status: one human-approved, three-job staged pilot digest sent. Inbox receipt
is confirmed by the user. Model ranking failed its promotion gate and remains disabled.
Unattended production is not accepted; no merge or scheduler enablement.**

## Four requested workstreams

| Workstream | Result | Remaining gate |
|---|---|---|
| Ranking/CV quality | Fictional 30-job ranking passed: P@5 1.0, pairwise 1.0 vs baseline 0.975; 105 requests. Initial CV suite passed 1/3 (41 requests); after a prompt correction all 3/3 passed (25 requests), with one revision. | Real-candidate ranking gate failed; reviewed CV previews preserve source facts but offer limited tailoring. |
| Live sources | Greenhouse and LinkedIn returned usable data; shared production normalization verifies duplicates. Indeed explicitly blocked with HTTP 403. | Accept reduced source coverage or provide an approved Indeed access route. |
| Email | Preview, simulated delivery and one real synthetic digest passed; inbox receipt confirmed by user screenshot. | Resolve OAuth testing-mode token lifetime before unattended production. |
| Deployment | Local backup/restore, repeated migrations, retained data and protected HTTP reads passed. Temporary API stopped. | Mac host chosen; dedicated DB and local restore/read checks passed. Off-host backup and alerts remain. |

Evidence: [sanitized report](../../evals/reports/pre_pilot_checkpoint05.json).
Synthetic fixture results are not real-candidate production quality estimates.
The unsuccessful CV cases remain failures; later diagnostic successes cannot erase
those observations or be represented as the original suite passing.

## Changes delivered

- Separate fictional profile/CV/30-job dataset and paced, request-capped evaluator;
  no dependency on personal CV content. CV diagnostics can capture fictional
  draft/reviewer outputs and deterministic checks without logging private prompts.
- Source acceptance exercises the same validation/canonicalization/deduplication
  helper as the actual scraper. Overlapping raw queries remain visible in reports.
- Reproducible disposable local deployment rehearsal and isolated one-shot delivery
  test, with a simulation mode that cannot contact Gmail.
- Personal Gmail OAuth setup helper requesting send-only access and saving secrets
  to ignored owner-only `.env`. No credential or downloaded OAuth JSON committed.
- Configurable `MASTER_CV_PATH` lets private evidence stay outside tracked files;
  live evaluator fingerprints now follow that configured source. Missing explicit
  files fail instead of silently falling back to older facts.
- The supplied PDF was visually checked, faithfully extracted and configured
  locally. Its personal contents remain untracked; subsequent Gemini checks were explicitly authorized.
  Degree completion status awaits confirmation; job-target preferences are unchanged.

## CV quality finding and correction

The diagnostic retained two unsupported drafts: an invented summary sentence and
an inferred target job title. The deterministic gate correctly rejected both. The
reviewer was also requesting missing job qualifications; prompts now separate
factual review from job-fit selection, require restoration of original statements,
and accept an unchanged CV with honest missing-skill warnings. Writer prompt is
`phase2-cv-v4`; specialist version is `specialists-v2`.

The repeat suite passed all three cases. The third needed one revision after
inventing PostgreSQL experience from a general skills entry. This demonstrates
the exercised safety/revision path, not a hallucination-free writer. Assistant
inspection confirmed final source fidelity; actual human CV acceptance is pending.

## Verification and next action

Implementation through `a6a22e5` passed CI #291 (189 tests; 30 CV gold cases), including credential
isolation, private-source selection, source deduplication, recovery and delivery.
See the final branch CI for subsequent report/diagnostic edits.

Gmail setup and the controlled real delivery test are complete. The supervised pilot
update below supersedes the earlier pre-pilot status. [Deployment preparation](PILOT_DEPLOYMENT.md) names
what the local rehearsal proves and what production still needs. Preserve private
reports/dumps locally; do not publish personal CVs, tokens or raw email evidence.

## Email acceptance update — 2026-10-08

Personal Gmail authorization completed. The first transport attempt failed while
the Gmail API was disabled; its rejection was reconciled using the recorded API
diagnostic. After activation, one controlled retry was acknowledged and exactly
one notification recorded. The user supplied an inbox screenshot confirming the
fictional digest arrived. No actual CV was sent, and no pilot/scheduler started.

## Real-candidate and supervised pilot update — 2026-10-08

The user authorized their private CV with Gemini and selected their Mac as host.
The four-role smoke passed in 13 requests. The 30-job real-candidate evaluation
used 164 bounded requests, including continuation after the first request cap.
Model Precision@5 was 0.8 and pairwise accuracy 0.96 versus baseline 1.0/1.0.
Labels were unchanged: promotion failed and automatic model ranking stays off.

Three captured live listings received writer/reviewer previews: all passed in
26 requests with no revisions. Final factual claim sets were unchanged from the
source CV. This supports conservative fidelity, not useful tailoring or verified
job qualifications; missing technical skills and degree-in-progress remain explicit.

A dedicated loopback PostgreSQL database on the Mac uses a non-superuser app
role. Repeated migrations, backup/restore and four protected read endpoints passed.
The user approved one digest after preview review. Gmail acknowledged one email
covering three jobs; the durable delivery is sent, three notifications are recorded,
and zero candidates remain for repeat delivery. The user confirmed inbox receipt on 2026-10-08.
This was a staged pilot using captured listings and reviewed previews, with zero
new model calls during delivery, not a fresh automated end-to-end pipeline run.
CVs remained local and were not attached. Scheduling remains off and PR #1 Draft.

Evidence: [sanitized real-candidate pilot report](../../evals/reports/real_cv_pilot_checkpoint05.json).
Implementation through `44d696e` passed CI #298, including configured private-CV
preflight coverage. Final documentation CI is tracked on the draft PR.

## Fresh supervised rehearsal — 2026-10-08

A broad LinkedIn attempt timed out. The narrower two-query capture returned six
listings: two had empty descriptions, one was previously emailed, and three were
selected. Greenhouse returned one valid listing below the shortlist threshold.
Source validation now rejects blank descriptions before deduplication; regression
coverage proves a complete duplicate can still be retained. CI for `3d07ac2` passed.

The three fresh candidates were fed into the real scheduler/persistence/ranking/CV
path in a separate local database, with delivery intercepted before any attempt.
The first single-writer run accepted one CV and withheld two for section-attribution
and unsupported-claim violations. Those failures remain recorded.

`CV_REVIEW_ENABLED=true` now enables the writer/reviewer loop independently of
`AGENT_WORKFLOW_ENABLED`, allowing deterministic ranking to remain selected.
A stage-aware retry accepted the two remaining CVs with no new scraping or ranking.
CI for `441fcba` passed. Preflight and live evaluators also honor the independent
reviewer selection. The exercised runs used 21 model requests across seven steps.

All three final CV bodies passed deterministic checks. Two retained the source
claim set; one omitted a teaching-assistant statement from the profile. Tailoring
utility remains limited. A model warning incorrectly inferred Python experience;
CV-body validation does not validate model commentary. Private human-review notes
flag that inference and proposed digest summaries use observed claim differences.
No new email, delivery attempt or notification was created. Private previews and a
database backup are saved; both local database servers are stopped. Hosting remains
deferred, and no scheduler or model-ranking promotion was enabled.

This is a bounded rehearsal using current-session capture and an intercepted send
boundary, not proof of an unmodified unattended pipeline. Evidence:
[fresh supervised report](../../evals/reports/fresh_supervised_checkpoint05.json).


### Approved fresh-batch delivery

After preview review, the user authorized the three-job digest. Gmail acknowledged
one email with the reviewed claim-difference summaries and no CV attachments.
Three notifications were recorded and zero candidates remained for repeat delivery.
No additional model calls were made. Inbox receipt is pending. The earlier no-send
rehearsal evidence remains unchanged; this is a separate approved delivery action.
A private post-delivery backup was saved. No scheduler or hosting change.


## Saved approval workflow — 2026-10-09

Migration 004 adds saved digest snapshots and approval/delivery state. The pipeline
now defaults to preparing a review batch, with separate approve/send actions in
the browser, authenticated API and CLI. Approval binds recipient, rendered email,
job requirements and CV versions; changed data or prior delivery prevents sending.
An ambiguous send remains blocked, and a reconciled not-sent attempt requires
fresh approval. Snapshot state and delivery-attempt admission commit atomically.

At this implementation checkpoint, reviewed emails excluded unverified model commentary and use a neutral
CV-review notice. The UI displays the captured requirements and exact CV bodies;
CVs are not attached. Unit/integration tests cover stale previews, concurrent sends,
crashes, reconciliation, authentication and MIME contents. A local browser rehearsal
used fictional responses and verified approval/send controls; no real mail or model
requests were made. See [workflow documentation](DIGEST_REVIEW.md).

Validation: 220 tests and lint passed locally; migration 004 applied and repeated
on the disposable database. [Sanitized verification report](../../evals/reports/saved_digest_review_checkpoint05.json).


## Observed CV differences and section emphasis — 2026-10-09

New saved previews and digest summaries describe computed source/output differences,
with an exact diff available in the review UI. Model-authored summaries, keywords
and warnings are retained only as unverified audit commentary. Existing version-1
snapshot approvals preserve their original neutral notice.

Complete sections now move by role family while retaining their wording and employer
context. The first live trial failed both cases (28 requests); unsupported rewrites
and evidence mapping errors were blocked, including one mistaken reviewer approval.
Writer v6 preserves complete source wording; workflow v3 clarifies evidence repair.
The bounded retry passed both captured engineering/product cases in 10 requests,
with all 42 source statements retained, no added/omitted passages and zero revisions.

Validation: 232 tests passed in CI for `bb410a8`; lint and fictional browser diff
preview checks passed. No email or database changes occurred in these quality trials.
This improves section emphasis, not qualification gaps or profile rewriting; human
usefulness acceptance and broader reliability remain open.
[Sanitized quality report](../../evals/reports/cv_section_emphasis_checkpoint05.json).


## Fresh saved-review pilot — 2026-10-09

A bounded fresh LinkedIn capture returned 12 rows; two missing descriptions were
rejected. Both previous delivery histories (six notifications) were checked before
selecting three new candidates. Existing pilot DB backups were saved before and
after. Production persistence, ranking, writer/reviewer and saved-review preparation
completed: 22 model requests, three valid CVs, all 42 source statements retained
in each, no added/omitted passages or revisions. The exact snapshot revalidated
and remains pending, with no new notifications or delivery attempts.

This exposes a matching-quality gap: high keyword scores coexist with significant
undocumented skill and experience requirements. Private review notes flag them;
these are not accepted matches or evidence of production readiness. Next quality
work should distinguish role relevance from verified qualification coverage.

The capture was bounded outside the scheduler; omitted-source zero counts are not
live failure evidence. This is not an unmodified end-to-end discovery run. Delivery
histories remain separate and were both checked. No scheduler, merge or email.
[Sanitized report](../../evals/reports/saved_review_live_checkpoint05.json).

## Qualification evidence triage — 2026-10-09

New saved previews distinguish role relevance from documented qualifications.
Deterministic extraction preserves requirement text, optional/required classification,
skill evidence excerpts and experience-duration review flags. No evidence is treated
as undocumented, not a hard mismatch; a keyword mention cannot certify proficiency.
Ranking events retain the assessment, and version-3 snapshots bind it into review
and email content. Version-1/2 approvals remain compatible. Ranking weights and
benchmark labels remain unchanged; qualification extraction is deliberately bounded.

Validation: full regression suite passed 240 tests, followed by an additional passing
regression for mixed mandatory/optional clauses (241 total). Lint and fictional
browser review/approval/send checks passed. Local replay of the three captured pilot
listings exposes undocumented Python in all three and preserves requirement context.
No live model requests or emails were needed. Human matching acceptance remains open.


## Consolidated evidence pilot — 2026-10-12

The private source now combines user-confirmed timeline corrections with technical
experience asserted in the supplied compendium. Counsellor examples and unresolved
financial claims remain excluded. No personal evidence is committed.

CV-only evaluation initially accepted one of three cases (24 requests); two failed
with provider service-unavailable errors. One bounded retry accepted both remaining
cases (20 requests). All three final CVs retain 56 source statements, no added or
omitted passages and zero revisions. Failures remain in the private evidence record.

The consolidated source is active locally. Three new CV versions and a revalidated
pending digest replace the older pending preview, preserving earlier versions and
backups before/after. No email or delivery attempt was created; databases stopped.
This reused captured listings, not a fresh availability check. These are full
evidence inventories with section ordering, not finished targeted two-page resumes.
Qualification and human usefulness acceptance remain open. No application code,
ranking settings, scheduler or hosting changes.
[Sanitized report](../../evals/reports/consolidated_source_checkpoint05.json).


## Bounded editorial delivery — 2026-10-12

Delivered two distinct, two-page resume review drafts (applied AI engineering and
technical fintech product management), editable text, and a ten-job review with
primary employer links, evidence, gaps and user ratings. All four PDF pages were
visually inspected; confirmed dates, degree-in-progress status and exclusion of
illustrative metrics were checked. The local rating interface was verified.

This is human editorial work, not a change to automatic generation or ranking.
Paraphrases are not claimed to have passed the conservative CV validator. Ten
listings were verified in current official employer pages/feeds; stale hits were
excluded. Editorial assessment is five prioritize, three conditional, two deprioritize.
The proposed eight-of-ten user acceptance target is not yet measured. One user
review/correction pass remains, then freeze this version and proceed to the
end-to-end pilot, retaining manual selection if needed. No fresh model calls,
email or application submissions. Personal artifacts remain private and untracked.
[Sanitized report](../../evals/reports/bounded_quality_review_checkpoint05.json).


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
