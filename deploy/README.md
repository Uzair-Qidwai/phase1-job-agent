# Cloud deployment package

Provider-neutral, single-VM Docker Compose package. No cloud resources are
provisioned by these files. Start only the API/database until release approval.
The database is persistent and has no published port. The API binds to host
loopback; private remote access or a separately configured HTTPS proxy is required.

## Before live deployment

1. Choose provider, region, budget, access method and alert destination.
2. Install a supported Docker Engine and Compose plugin on the Linux host.
3. Create a private secrets directory outside the checkout/image, owned by the
   deployment operator with mode 0700. Set `JOB_AGENT_SECRETS_DIR` to its absolute path.
4. Create `app.env` from `deploy/app.env.example`; replace placeholders and verify
   provider model availability/prices/quotas. The example does not authorize live calls.
5. Place confirmed evidence in `master-cv.md` and distinct random passwords in
   `db-password` and `db-admin-password`. Do not put credentials in shell arguments.
6. Make mounted files readable by container UIDs. For this Compose file-secrets
   setup, mode 0444 files inside the private 0700 directory work; directory traversal
   stays restricted on the host. Docker administrators can access these secrets.
   Compose file mounts do not provide an encrypted secret-management service.
7. Resolve durable Gmail OAuth and consolidate existing pilot histories before
   migration. A fresh database is not a substitute for delivery-history migration.

The image contains application code, migrations and candidate preferences, but no
master CV, OAuth token, `.env`, local reports or database dumps. Dependencies are
hash-locked, and base app/database images are pinned by digest. OS packages fetched
when installing browser dependencies can still change; preserve the validated
image digest for each actual release.

## Build and start without scheduling

Run from the repository root with the secrets directory already configured:

```bash
docker compose -f deploy/compose.yaml config --quiet
docker compose -f deploy/compose.yaml build api
docker compose -f deploy/compose.yaml up -d --wait api
```

Database health gates the migration service; successful migration gates API startup.
The app uses a dedicated non-superuser database role. The startup wrapper constructs
its database URL from the mounted password, forces protected reads and review-mode
delivery, and fixes the evidence path to the mounted file. It loads secrets only
at process startup, not into image layers or Compose environment configuration.
A separate API process can launch the existing admitted pipeline subprocess in the
same container; no queue or separate worker server is required for this release.

The authenticated health probe checks HTTP and database access. Docker restart
policies restart exited services, not merely unhealthy ones. External monitoring,
backup scheduling and alert delivery are still required before production.
Logs rotate at three 10 MB files per service. The application runs as UID 10001
with a read-only filesystem, temporary writable directories and dropped capabilities.
The Chromium browser smoke checks launchability, not a guarantee that job sites
will allow cloud scraping. Browser sandbox behavior needs deployment-host review;
container isolation does not make untrusted browsing risk-free.

## Manual run and review

Only after live credentials, quotas and evidence consent have been checked:

```bash
docker compose -f deploy/compose.yaml exec api python /app/deploy/entrypoint.py python -m src.scheduler --run-now
```

Review at `/review` through the configured access path. Approval and sending remain
separate explicit actions. No scheduler or email is triggered by `up api`.
The full four-agent ranking workflow remains off in the example configuration.
The earlier pilot used additional model-request pacing; cloud quota behavior must
be checked before turning on the schedule.

## Scheduler: release-only action

The scheduler has both an opt-in Compose profile and a startup guard. Keep
`ENABLE_SCHEDULER=false` until release approval. Once approved, set it to `true`
in the private app.env, confirm timezone and run time, then start the `scheduled`
profile. Starting the service can run the daily pipeline; do not use it as a smoke test.

## Upgrades and rollback

Back up the database off-host and verify restore first. Preserve the validated
application image. Stop the scheduler before upgrades, rebuild or select
`JOB_AGENT_IMAGE`, and rerun migrations with `docker compose ... run --rm migrate`
before recreating app services. Migration files are checksum-protected. Do not
assume an older application works with a newer schema; rollback may require a
reviewed forward fix or restoring the pre-upgrade backup with sending disabled.

`docker compose down` preserves the named database volume. **Do not use `down -v`
on a live deployment.** PostgreSQL initialization and role passwords run only on
an empty volume; changing password files alone does not rotate existing DB roles.
Coordinate password rotation with database changes and app recreation.

## Validation

`bash deploy/smoke.sh` creates a uniquely named disposable stack with fictional
credentials and data. It builds the image, applies/repeats migrations, tests
unauthenticated denial and authenticated reads, launches Chromium on an offline
page, verifies the scheduler guard, and checks data survival across service
recreation. It makes no model or Gmail calls and deletes only its own test volume.
The GitHub `deployment-smoke` CI job runs this check on Linux.

Remaining release gates: provider/host setup, data consolidation, secret/OAuth
installation, cloud source/model checks, off-host backup restore, independent
alerts, exact digest approval and final merge/schedule authorization.
