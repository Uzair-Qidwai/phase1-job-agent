# Checkpoint 5 — pre-pilot review

Date: 2026-10-08. Branch: `phase2-foundation`. PR #1 remains Draft.

**Status: checkpoint of tested progress and remaining gates. The pilot is not
started, and steps 1–4 are not all accepted yet. No merge or scheduler enablement.**

## Four requested workstreams

| Workstream | Result | Remaining gate |
|---|---|---|
| Ranking/CV quality | Fictional 30-job ranking passed: P@5 1.0, pairwise 1.0 vs baseline 0.975; 105 requests. Initial CV suite passed 1/3 (41 requests); after a prompt correction all 3/3 passed (25 requests), with one revision. | Real-candidate evaluation and human review remain pending. |
| Live sources | Greenhouse and LinkedIn returned usable data; shared production normalization verifies duplicates. Indeed explicitly blocked with HTTP 403. | Accept reduced source coverage or provide an approved Indeed access route. |
| Email | Preview, simulated delivery and one real synthetic digest passed; inbox receipt confirmed by user screenshot. | Resolve OAuth testing-mode token lifetime before unattended production. |
| Deployment | Local backup/restore, repeated migrations, retained data and protected HTTP reads passed. Temporary API stopped. | Confirm host, production DB access/backup/alerts and target-host recovery. |

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
  locally. Its personal contents remain untracked and were not sent to Gemini.
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

Gmail setup and the controlled real delivery test are complete. Resolve the outstanding quality/hosting decisions
before advancing to the pilot. [Deployment preparation](PILOT_DEPLOYMENT.md) names
what the local rehearsal proves and what production still needs. Preserve private
reports/dumps locally; do not publish personal CVs, tokens or raw email evidence.

## Email acceptance update — 2026-10-08

Personal Gmail authorization completed. The first transport attempt failed while
the Gmail API was disabled; its rejection was reconciled using the recorded API
diagnostic. After activation, one controlled retry was acknowledged and exactly
one notification recorded. The user supplied an inbox screenshot confirming the
fictional digest arrived. No actual CV was sent, and no pilot/scheduler started.
