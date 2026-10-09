"""FastAPI dashboard and protected REST API for the Phase 2 job agent."""

from __future__ import annotations

import logging
import secrets
import subprocess
import sys
from pathlib import Path
from html import escape
from typing import Optional
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.settings import get_settings
from src.tracker import (
    PIPELINE_RUN_PUBLIC_FIELDS,
    VALID_PIPELINE_STATUSES,
    get_pipeline_runs,
    get_source_health,
    PipelineAlreadyRunning,
    fail_pipeline_run,
    start_pipeline_run,
    add_note,
    get_active_pipeline_run,
    get_job_by_id,
    get_jobs,
    get_pipeline_run,
    update_job_status,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Job Search Agent", version="2.0.0")


class StatusUpdate(BaseModel):
    status: str


class NoteUpdate(BaseModel):
    notes: str


def require_write_auth(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.api_token:
        raise HTTPException(
            status_code=503,
            detail="API_TOKEN is not configured; write operations are disabled",
        )

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(token, settings.api_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _safe_http_url(value: str) -> str:
    parts = urlsplit(value or "")
    if parts.scheme.casefold() not in {"http", "https"}:
        return "#"
    if not parts.netloc:
        return "#"
    return value


@app.middleware("http")
async def security_headers(request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith(("/digests", "/review")):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    return response


def require_read_auth(authorization: str | None = Header(default=None)) -> None:
    if get_settings().api_require_read_auth:
        require_write_auth(authorization)


class DigestSelection(BaseModel):
    job_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=20)
    limit: int = Field(default=5, ge=1, le=20)


class DigestApproval(BaseModel):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def _review_action(action, *args, **kwargs):
    from src.delivery import DeliveryAmbiguous
    try:
        return action(*args, **kwargs)
    except (ValueError, PipelineAlreadyRunning, DeliveryAmbiguous) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@app.get("/review", response_class=HTMLResponse)
def review_page():
    # Public shell only. All private data and actions below always require auth.
    return HTMLResponse(Path(__file__).with_name("review_page.html").read_text())


@app.get("/digests", dependencies=[Depends(require_write_auth)])
def digest_batches(limit: int = Query(20, ge=1, le=100)):
    from src.digest_review import list_batches
    return list_batches(limit)


@app.post("/digests", dependencies=[Depends(require_write_auth)])
def prepare_digest(selection: DigestSelection):
    from src.digest_review import prepare_batch
    ids = [str(j) for j in selection.job_ids] if selection.job_ids else None
    return _review_action(prepare_batch, ids, limit=selection.limit)


@app.get("/digests/{batch_id}", dependencies=[Depends(require_write_auth)])
def digest_batch(batch_id: UUID):
    from src.digest_review import get_batch
    return _review_action(get_batch, str(batch_id))


@app.post("/digests/{batch_id}/approve", dependencies=[Depends(require_write_auth)])
def approve_digest(batch_id: UUID, approval: DigestApproval):
    from src.digest_review import approve_batch
    return _review_action(approve_batch, str(batch_id), approval.fingerprint)


@app.post("/digests/{batch_id}/send", dependencies=[Depends(require_write_auth)])
def send_approved_digest(batch_id: UUID, approval: DigestApproval):
    from src.digest_review import send_batch
    return {"jobs_notified": _review_action(send_batch, str(batch_id), approval.fingerprint)}


@app.post("/digests/{batch_id}/cancel", dependencies=[Depends(require_write_auth)])
def cancel_digest(batch_id: UUID):
    from src.digest_review import cancel_batch
    _review_action(cancel_batch, str(batch_id))
    return {"status": "cancelled"}


@app.get("/jobs", dependencies=[Depends(require_read_auth)])
def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(200, ge=1, le=500),
):
    return get_jobs(status=status, min_score=min_score, limit=limit)


@app.get("/jobs/{job_id}", dependencies=[Depends(require_read_auth)])
def get_job(job_id: UUID):
    job = get_job_by_id(str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.patch("/jobs/{job_id}/status", dependencies=[Depends(require_write_auth)])
def patch_status(job_id: UUID, body: StatusUpdate):
    try:
        updated = update_job_status(str(job_id), body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return updated


@app.patch("/jobs/{job_id}/notes", dependencies=[Depends(require_write_auth)])
def patch_notes(job_id: UUID, body: NoteUpdate):
    updated = add_note(str(job_id), body.notes)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}


@app.get("/pipeline/runs", dependencies=[Depends(require_read_auth)])
def list_pipeline_runs(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100000),
):
    if status is not None and status not in VALID_PIPELINE_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid pipeline status")
    rows = get_pipeline_runs(status=status, limit=limit, offset=offset)
    return [{key: row.get(key) for key in PIPELINE_RUN_PUBLIC_FIELDS} for row in rows]


@app.get("/pipeline/runs/{run_id}", dependencies=[Depends(require_read_auth)])
def read_pipeline_run(run_id: UUID):
    run = get_pipeline_run(str(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return {key: run.get(key) for key in PIPELINE_RUN_PUBLIC_FIELDS}


@app.get("/deliveries", dependencies=[Depends(require_write_auth)])
def read_delivery_attempts(limit: int = Query(20, ge=1, le=100)):
    from src.delivery import list_attempts
    fields = ("id", "run_id", "message_id", "status", "created_at", "resolved_at")
    return [{key: row[key] for key in fields} for row in list_attempts(limit)]


@app.get("/sources/health", dependencies=[Depends(require_read_auth)])
def list_source_health(
    source: str | None = Query(None, min_length=1, max_length=100),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100000),
):
    return get_source_health(source=source, limit=limit, offset=offset)


@app.post("/pipeline/runs/{run_id}/retry", dependencies=[Depends(require_write_auth)])
def retry_pipeline(run_id: UUID):
    active = get_active_pipeline_run()
    if active:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Pipeline already running",
                "run_id": str(active["id"]),
                "stage": active["current_stage"],
            },
        )

    failed = get_pipeline_run(str(run_id))
    if not failed:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    if failed["status"] != "failed":
        raise HTTPException(
            status_code=409,
            detail="Only failed pipeline runs can be retried",
        )

    admitted_id = _launch_pipeline("retry", retry_of_run_id=str(run_id))
    return {
        "status": "pipeline retry accepted",
        "run_id": admitted_id,
        "retry_of_run_id": str(run_id),
        "failed_stage": failed["current_stage"],
    }


def _launch_pipeline(trigger: str, *, retry_of_run_id: str | None = None) -> str:
    # Reserve before spawning: the unique active-run index arbitrates across
    # threads, HTTP workers, CLI processes, and scheduled runs.
    try:
        run_id = start_pipeline_run(trigger, retry_of_run_id=retry_of_run_id)
    except PipelineAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail="Pipeline already running") from exc
    try:
        subprocess.Popen(
            [sys.executable, "-m", "src.scheduler", "--admitted-run", run_id],
            cwd=Path(__file__).resolve().parent.parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        fail_pipeline_run(run_id, "created", exc)
        raise HTTPException(status_code=503, detail="Pipeline could not be launched") from exc
    return run_id


@app.post("/pipeline/run", dependencies=[Depends(require_write_auth)])
def trigger_pipeline():
    run_id = _launch_pipeline("manual")
    return {"status": "pipeline trigger accepted", "run_id": run_id}


STATUSES = ["new", "applied", "interview", "offer", "rejected"]
STATUS_COLORS = {
    "new": "#3b82f6",
    "applied": "#8b5cf6",
    "interview": "#f59e0b",
    "offer": "#22c55e",
    "rejected": "#ef4444",
}


def _score_color(score: float | None) -> str:
    if score is None:
        return "#94a3b8"
    if score >= 0.8:
        return "#22c55e"
    if score >= 0.6:
        return "#f59e0b"
    return "#ef4444"


@app.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(require_read_auth)])
def dashboard(
    status: Optional[str] = Query(None),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
):
    jobs = get_jobs(status=status, min_score=min_score)

    status_tabs = ""
    for state in ["all"] + STATUSES:
        active = (status is None and state == "all") or status == state
        href = "/dashboard" if state == "all" else f"/dashboard?status={state}"
        bg = "#1e293b" if active else "#f1f5f9"
        fg = "white" if active else "#475569"
        status_tabs += (
            f'<a href="{href}" style="padding:6px 14px;border-radius:6px;'
            f'background:{bg};color:{fg};text-decoration:none;font-size:13px;">'
            f"{escape(state.title())}</a> "
        )

    rows = ""
    for job in jobs:
        score = job.get("match_score")
        score_str = f"{score:.0%}" if score is not None else "—"
        score_col = _score_color(score)
        current_status = str(job.get("status") or "new")
        status_col = STATUS_COLORS.get(current_status, "#94a3b8")
        job_id = escape(str(job["id"]), quote=True)
        title = escape(str(job.get("title") or ""), quote=True)
        company = escape(str(job.get("company") or ""), quote=True)
        location = escape(str(job.get("location") or "—"), quote=True)
        source = escape(str(job.get("source") or "").title(), quote=True)
        changes = escape(str(job.get("changes_made") or "—")[:120], quote=True)
        safe_url = escape(_safe_http_url(str(job.get("url") or "")), quote=True)

        options = "".join(
            f'<option value="{state}" '
            f'{"selected" if state == current_status else ""}>{state.title()}</option>'
            for state in STATUSES
        )

        rows += f"""
        <tr>
          <td style="padding:10px 14px;">
            <a href="{safe_url}" target="_blank" rel="noopener noreferrer"
               style="color:#3b82f6;font-weight:600;text-decoration:none;">
              {title}
            </a><br>
            <small style="color:#64748b;">{company} · {location}</small>
          </td>
          <td style="padding:10px 14px;text-align:center;">
            <span style="background:{score_col};color:white;padding:2px 10px;
                         border-radius:999px;font-size:12px;font-weight:600;">
              {score_str}
            </span>
          </td>
          <td style="padding:10px 14px;text-align:center;">
            <select onchange="updateStatus('{job_id}', this.value)"
                    style="border:1px solid #e2e8f0;padding:4px 8px;border-radius:6px;
                           background:white;color:{status_col};font-weight:600;cursor:pointer;">
              {options}
            </select>
          </td>
          <td style="padding:10px 14px;font-size:12px;color:#64748b;">{source}</td>
          <td style="padding:10px 14px;font-size:12px;color:#64748b;max-width:220px;">
            {changes}
          </td>
        </tr>
        """

    if not rows:
        rows = (
            '<tr><td colspan="5" style="text-align:center;padding:40px;'
            'color:#94a3b8;">No jobs found</td></tr>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Job Search Dashboard</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
             background: #f8fafc; color: #1e293b; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ background: #f1f5f9; font-size: 11px; text-transform: uppercase;
          letter-spacing: .05em; color: #64748b; padding: 10px 14px; text-align: left; }}
    tr:hover {{ background: #f8fafc; }}
    input {{ border:1px solid #cbd5e1;padding:8px 10px;border-radius:8px;min-width:220px; }}
  </style>
</head>
<body>
  <div style="max-width:1100px;margin:0 auto;padding:24px;">
    <div style="display:flex;gap:12px;align-items:center;justify-content:space-between;
                flex-wrap:wrap;margin-bottom:20px;">
      <div>
        <h1 style="font-size:22px;font-weight:700;">Job Search Dashboard</h1>
        <a href="/review">Review saved digests</a>
        <p style="color:#64748b;font-size:14px;">{len(jobs)} jobs</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <input id="apiToken" type="password" autocomplete="off"
               placeholder="API token for write actions">
        <button type="button" onclick="triggerPipeline(this)"
                style="background:#1e293b;color:white;border:none;padding:8px 16px;
                       border-radius:8px;cursor:pointer;font-size:13px;">
          Run Pipeline Now
        </button>
      </div>
    </div>

    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;">
      {status_tabs}
    </div>

    <div style="background:white;border-radius:12px;overflow:hidden;
                box-shadow:0 1px 3px rgba(0,0,0,.08);">
      <table>
        <thead>
          <tr>
            <th>Role</th><th>Score</th><th>Status</th><th>Source</th><th>CV Changes</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </div>

  <script>
    function writeHeaders() {{
      const token = document.getElementById('apiToken').value;
      return {{
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token
      }};
    }}

    async function updateStatus(jobId, newStatus) {{
      const resp = await fetch('/jobs/' + jobId + '/status', {{
        method: 'PATCH',
        headers: writeHeaders(),
        body: JSON.stringify({{ status: newStatus }})
      }});
      if (!resp.ok) alert('Failed to update status: ' + resp.status);
    }}

    async function triggerPipeline(btn) {{
      btn.textContent = 'Starting…';
      btn.disabled = true;
      const resp = await fetch('/pipeline/run', {{
        method: 'POST',
        headers: writeHeaders()
      }});
      if (!resp.ok) alert('Pipeline trigger failed: ' + resp.status);
      btn.textContent = 'Run Pipeline Now';
      btn.disabled = false;
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=True)
