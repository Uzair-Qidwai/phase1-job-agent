# Checkpoint 6 — Cloud deployment packaging

Date: October 18, 2026. Branch: `phase2-foundation`; PR #1 remains draft.
Implementation: `235f8aa94a2b2ff745670a3f574ad281a5e5a268`.

## Delivered

- Pinned Python/PostgreSQL images and hash-locked runtime dependencies.
- Separate API, migration, optional scheduler and PostgreSQL Compose services.
- Persistent database, non-superuser app account, private DB port and loopback API.
- Non-root, read-only app containers; secrets and private CV outside the image.
- Deployment wrapper enforces read authentication and digest review mode.
- Scheduler requires explicit service selection and an enabled configuration flag.
- Instructions cover secrets, startup, upgrades, rollback and release gates.

## Verification

[PR CI](https://github.com/Uzair-Qidwai/phase1-job-agent/actions/runs/39171204208)
and [push CI](https://github.com/Uzair-Qidwai/phase1-job-agent/actions/runs/39171200773)
passed: 266 tests, lint, offline acceptance and Linux deployment smoke checks.
The smoke test built the image, applied and repeated migrations, checked protected
reads and DB role privileges, launched Chromium offline, preserved a fictional row
across restart and confirmed disabled scheduler startup was refused. It removed
its disposable volume afterward. No real model or email calls were made.

This proves container operability, not cloud acceptance, browser sandbox security,
production capacity or disaster recovery. The local Docker engine was stopped;
container verification ran in GitHub Linux CI.

## Remaining

Select provider, region, budget and access method; provision host; install private
settings and CV; resolve durable Gmail OAuth; consolidate pilot histories and
pending batches; verify cloud source access and provider quotas; configure off-host
backups with restore checks and independent alerts. Review the exact digest and
authorize any send, then approve release/merge and scheduling.

No cloud resources were provisioned, scheduler enabled or email sent.
See [deployment guide](../../deploy/README.md). No repeat local tuning cycle is
required merely to reproduce completed pilot evidence.
