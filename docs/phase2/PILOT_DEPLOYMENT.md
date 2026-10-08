# Deployment preparation before the pilot

Current target is a **local Mac rehearsal**, not an installed production service.
Hosting choice is still unconfirmed. No scheduler is installed or running.

## Verified locally

`python -m evals.deployment_rehearsal --allow-local --output .local/deployment-NEW.json`
creates two uniquely named databases in the local test PostgreSQL on port 55439.
It applies migrations twice, backs up a fictional job and migration history,
restores to a separate DB, reapplies migrations twice, compares retained data,
and starts a temporary loopback API with a generated token. Protected jobs,
run history, source health and delivery reads must reject missing authentication
and succeed with the token. It then stops the API. Databases and owner-only dump
remain for investigation. It never runs the pipeline or sends mail.

This rehearses backup-based rollback to a separate database and API operation.
It does not prove a remote host, remote backups or recovery of real production data.
The existing process-death/recovery suite remains the worker-recovery evidence.

## Configuration for an initial manual pilot

Use a dedicated database, direct PostgreSQL/session pooling, a least-privilege
application account, and a separate migration owner where the host supports it.
The disposable rehearsal's local postgres role is not a production configuration.
Keep secrets in a private local environment/host secret store; never commit them.

- API: bind `127.0.0.1`; set `API_REQUIRE_READ_AUTH=true` and a random `API_TOKEN`.
  Do not publish a port or put the token in a dashboard URL. Browser dashboard
  access requires a trusted authenticated proxy; API-only operation can use headers.
- Keep `RANKING_MODE=deterministic` and `AGENT_WORKFLOW_ENABLED=false` until actual
  candidate matching has been evaluated and approved. Synthetic success alone
  cannot promote the actual candidate workflow.
- Retain request limits and honest pricing. Synthetic free-tier tests explicitly
  use paced requests; normal runtime does not yet guarantee project-wide pacing.
  Start with one small manually supervised run; quota errors must not trigger
  unlimited retries or an automatic vendor switch.
- Configure sender OAuth, recipient, source availability and reviewed candidate
  facts before a real run. The real CV/free-tier data-use choice remains pending.
- The current schedule setting is 08:00 America/Toronto. Do not start
  `python -m src.scheduler` until the pilot decision; it installs the daily job
  in that process. A Mac must stay awake and connected for that schedule.

## Operator checks and release gates

1. Confirm the host and deploy the reviewed branch revision with pinned model SDKs.
2. Configure DB access/secrets and rehearse backup restore on that host. Store
   backups off-host with restricted access; choose retention and verify restoration.
3. Inspect authenticated `/pipeline/runs`, `/sources/health` and `/deliveries`.
   Investigate failed runs, repeated zero-result sources and unresolved deliveries.
   These endpoints provide status; independent alert delivery is not configured yet.
4. Complete the one real email test and confirm inbox receipt. Resolve OAuth
   testing-mode token expiry before unattended operation.
5. Choose acceptable handling of Indeed's observed access block (exclude it from
   pilot expectations or provide an approved source). Do not bypass the block.
6. Review real candidate ranking/CVs, then approve a small manual pilot. Inspect
   every CV and digest. Set the initial batch and call caps before starting it.
7. After the pilot, decide on scheduling, production hosting and final PR approval.
   Merge to main and enabling unattended work remain separate user decisions.

For a failed release: stop entrypoints/scheduler/workers; retain delivery evidence;
restore the verified backup into a new DB; switch the matching code/config to it.
Follow [OPERATIONS.md](OPERATIONS.md) for ambiguous sends and stranded runs before
retrying. Never assume restoring a DB means an external email was not sent.
