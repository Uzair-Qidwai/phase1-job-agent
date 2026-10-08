# Phase 2 Checkpoint 2 — Admission, migrations, operations, factuality

Date: 2026-10-08. Branch: `phase2-foundation`. PR #1 remains Draft, targeting
`main`. No merge is authorized. Baseline: Checkpoint 1, `e55b95b`, CI #246.

## Completed slices

| Slice | Commit | Passing PR CI |
| --- | --- | --- |
| Reserve HTTP admission before spawning; claim once | `152fec8` | #248 |
| Ordered migrations with checksum ledger and transaction lock | `3c6225b` | #250 |
| Bounded operational history endpoints | `811466e` | #252 |
| Whole-output CV coverage and qualifier checks | `aeb2db3` | #254 |

HTTP admission uses the existing unique active-run index across HTTP workers,
CLI invocations, and scheduled runs. Retry reservations retain lineage and are
consumed atomically once. Spawn and initialization errors release the slot by
recording failure. Tests cover eight simultaneous HTTP requests, duplicate
claims, failures, and end-to-end admitted notification recovery without scraping.

The lightweight migration runner stores ordered filenames and hashes, rejects
changed/missing history, serializes concurrent runners, and rolls back an entire
failed batch. Existing SQL files are unchanged. CI exercises legacy adoption and
repeatability; integration tests cover ordering, drift, rollback and concurrency.
Use `python -m src.migrations` from a repository checkout before service startup.

Read endpoints: `/pipeline/runs`, `/pipeline/runs/{uuid}`, `/sources/health`.
History responses have filters and bounded pagination; run fields omit raw
exception messages, metadata and event payloads. Reads follow the existing
private-network/unauthenticated policy. They do not trigger work.

## CV validation contract v2

Prompt `phase2-cv-v2`; validation `deterministic-cv-v2`. Each output sentence,
bullet and substantive heading is checked. Copied complete source statements
are covered automatically; rewrites require a matching full output claim and
an exact quote of complete supporting source statements. Every factual term in
a rewrite must occur in one cited statement; protected qualifiers and negation
must survive. Existing numeric checks remain, with statement-level coverage
preventing unrelated numbers from being reused. Candidate profiles currently
contain search preferences, so they cannot establish experience or credentials.

The expanded deterministic gold set includes supported copying/shortening and
negative cases for uncited awards, invented employers/skills, role inflation,
expected credentials, applicant status, negation, truncated quotes, detached
citations, factual headings, single-digit tenure, and transferred metrics.
Generation rejects failed validation before returning a CV for persistence.
Validation metadata records version, output claim count and unsupported claims.

## Deliberate limits and remaining exit work

- This is a conservative lexical gate, not semantic entailment. Valid synonyms
  can be rejected; reordered words, relationships within a statement, or moving
  copied statements across sections can still change meaning. Human review is
  required. Broader semantic evals remain future work; do not advertise complete
  factuality guarantees.
- Abrupt host/interpreter termination can strand an active run, including an
  unclaimed reservation. Verify no worker is alive before operator recovery.
  Automatic expiry is deferred because expiring a live worker could permit
  duplicate execution.
- Migration files require a source checkout and transactional SQL; downgrades
  and out-of-band schema drift detection are not implemented.
- Offset pages may shift during concurrent inserts. Source zero counts are
  observations, not a full upstream availability diagnosis.
- The existing external email delivery crash window remains: database delivery
  records cannot prove exactly-once delivery across an external provider call.
- Review the complete Phase 2 acceptance criteria and explicitly accept remaining
  operational/security debt before moving the PR out of Draft.

## Validation

Full local suite: 117 tests and deterministic evals pass against a freshly
migrated isolated PostgreSQL database; a second migration run is a no-op. CI
uses Python 3.11/PostgreSQL 16. Implementation commit `aeb2db31557bc7cb2db1edbe940e4198e4e06092` passed
[CI #254](https://github.com/Uzair-Qidwai/phase1-job-agent/actions/runs/37735378495)
with 117 tests. No live provider calls,
scraping, or email delivery were used for these tests.
