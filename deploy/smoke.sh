#!/usr/bin/env bash
# Disposable CI stack only: synthetic credentials/data, no provider or email calls.
set -euo pipefail
export JOB_AGENT_SECRETS_DIR="$(mktemp -d)"
export COMPOSE_PROJECT_NAME="job-agent-smoke-${RANDOM}"
compose() { docker compose -p "$COMPOSE_PROJECT_NAME" -f deploy/compose.yaml "$@"; }
cleanup() {
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$JOB_AGENT_SECRETS_DIR"
}
trap cleanup EXIT
python3 - <<'PY'
import os,secrets
from pathlib import Path
p=Path(os.environ['JOB_AGENT_SECRETS_DIR'])
(p/'app.env').write_text('API_TOKEN='+secrets.token_urlsafe(32)+'\nENABLE_SCHEDULER=false\n')
(p/'db-password').write_text(secrets.token_urlsafe(32))
(p/'db-admin-password').write_text(secrets.token_urlsafe(32))
(p/'master-cv.md').write_text('# Fictional Candidate\nPython developer.\n')
for f in p.iterdir(): f.chmod(0o444)
PY
compose build api
compose up -d --wait api
# The optional scheduler must not be running.
test -z "$(compose ps -q scheduler)"
compose run --rm --no-deps api python -c '
import os,urllib.request,urllib.error
from src.tracker import get_conn
try:
 urllib.request.urlopen("http://api:8000/jobs")
 raise AssertionError("Unauthenticated access allowed")
except urllib.error.HTTPError as exc:
 assert exc.code == 401
request=urllib.request.Request("http://api:8000/jobs",headers={"Authorization":"Bearer "+os.environ["API_TOKEN"]})
assert urllib.request.urlopen(request).status==200
with get_conn() as c,c.cursor() as cur:
 cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
 assert cur.fetchone()["rolsuper"] is False
 cur.execute("INSERT INTO jobs (title,company,location,url,source,description) VALUES (%s,%s,%s,%s,%s,%s)",("Smoke","Fictional","Toronto","https://example.com/container-smoke","fixture","Synthetic"))
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 page=b.new_page();page.goto("data:text/html,<title>smoke</title>")
 assert page.title()=="smoke"
 b.close()
'
compose run --rm migrate
if compose run --rm --no-deps scheduler; then
  echo 'Scheduler guard unexpectedly allowed startup' >&2
  exit 1
fi
compose down
compose up -d --wait api
compose run --rm --no-deps api python -c '
from src.tracker import get_conn
with get_conn() as c,c.cursor() as cur:
 cur.execute("SELECT count(*) AS n FROM jobs WHERE source=%s",("fixture",))
 assert cur.fetchone()["n"]==1
'
echo 'Container smoke passed: auth, migrations, browser, persistence and scheduler guard.'
