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
