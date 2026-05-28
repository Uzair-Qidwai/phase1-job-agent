"""
api.py — FastAPI dashboard + REST API.

Endpoints:
  GET  /jobs                 → JSON list of jobs (filters: status, min_score)
  GET  /jobs/{id}            → single job detail with tailored CV
  PATCH /jobs/{id}/status    → update status  {"status": "applied"}
  PATCH /jobs/{id}/notes     → update notes   {"notes": "..."}
  GET  /dashboard            → HTML dashboard (filterable, sortable)
  POST /pipeline/run         → trigger pipeline immediately (dev use)
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.tracker import (
    get_jobs,
    get_job_by_id,
    update_job_status,
    add_note,
)

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="Phase 1 — Job Search Agent", version="1.0.0")


# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str

class NoteUpdate(BaseModel):
    notes: str


# ─────────────────────────────────────────────
# REST endpoints
# ─────────────────────────────────────────────

@app.get("/jobs")
def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(200, ge=1, le=500),
):
    return get_jobs(status=status, min_score=min_score, limit=limit)


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.patch("/jobs/{job_id}/status")
def patch_status(job_id: str, body: StatusUpdate):
    try:
        updated = update_job_status(job_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return updated


@app.patch("/jobs/{job_id}/notes")
def patch_notes(job_id: str, body: NoteUpdate):
    add_note(job_id, body.notes)
    return {"ok": True}


@app.post("/pipeline/run")
def trigger_pipeline():
    """Non-blocking pipeline trigger for dev / manual runs."""
    subprocess.Popen(
        [sys.executable, "-m", "src.scheduler", "--run-now"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"status": "pipeline started"}


# ─────────────────────────────────────────────
# HTML dashboard
# ─────────────────────────────────────────────

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


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    status: Optional[str] = Query(None),
    min_score: float = Query(0.0),
):
    jobs = get_jobs(status=status, min_score=min_score)

    status_tabs = ""
    for s in ["all"] + STATUSES:
        active = (status is None and s == "all") or status == s
        href = "/dashboard" if s == "all" else f"/dashboard?status={s}"
        bg = "#1e293b" if active else "#f1f5f9"
        fg = "white" if active else "#475569"
        status_tabs += (
            f'<a href="{href}" style="padding:6px 14px;border-radius:6px;'
            f'background:{bg};color:{fg};text-decoration:none;font-size:13px;">{s.title()}</a> '
        )

    rows = ""
    for job in jobs:
        score = job.get("match_score")
        score_str = f"{score:.0%}" if score is not None else "—"
        score_col = _score_color(score)
        status_col = STATUS_COLORS.get(job["status"], "#94a3b8")
        rows += f"""
        <tr>
          <td style="padding:10px 14px;">
            <a href="{job['url']}" target="_blank"
               style="color:#3b82f6;font-weight:600;text-decoration:none;">
              {job['title']}
            </a><br>
            <small style="color:#64748b;">{job['company']} · {job.get('location','—')}</small>
          </td>
          <td style="padding:10px 14px;text-align:center;">
            <span style="background:{score_col};color:white;padding:2px 10px;
                         border-radius:999px;font-size:12px;font-weight:600;">
              {score_str}
            </span>
          </td>
          <td style="padding:10px 14px;text-align:center;">
            <select onchange="updateStatus('{job['id']}', this.value)"
                    style="border:1px solid #e2e8f0;padding:4px 8px;border-radius:6px;
                           background:white;color:{status_col};font-weight:600;cursor:pointer;">
              {"".join(
                f'<option value="{s}" {"selected" if s == job["status"] else ""}>{s.title()}</option>'
                for s in STATUSES
              )}
            </select>
          </td>
          <td style="padding:10px 14px;font-size:12px;color:#64748b;">
            {job.get('source','').title()}
          </td>
          <td style="padding:10px 14px;font-size:12px;color:#64748b;max-width:220px;">
            {(job.get('changes_made') or '—')[:120]}
          </td>
        </tr>
        """

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
  </style>
</head>
<body>
  <div style="max-width:1100px;margin:0 auto;padding:24px;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;">
      <div>
        <h1 style="font-size:22px;font-weight:700;">📋 Job Search Dashboard</h1>
        <p style="color:#64748b;font-size:14px;">{len(jobs)} jobs</p>
      </div>
      <button onclick="triggerPipeline()"
              style="background:#1e293b;color:white;border:none;padding:8px 16px;
                     border-radius:8px;cursor:pointer;font-size:13px;">
        ▶ Run Pipeline Now
      </button>
    </div>

    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;">
      {status_tabs}
    </div>

    <div style="background:white;border-radius:12px;overflow:hidden;
                box-shadow:0 1px 3px rgba(0,0,0,.08);">
      <table>
        <thead>
          <tr>
            <th>Role</th>
            <th>Score</th>
            <th>Status</th>
            <th>Source</th>
            <th>CV Changes</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      {('<tr><td colspan="5" style="text-align:center;padding:40px;color:#94a3b8;">No jobs found</td></tr>'
         if not jobs else '')}
    </div>
  </div>

  <script>
    async function updateStatus(jobId, newStatus) {{
      const resp = await fetch(`/jobs/${{jobId}}/status`, {{
        method: 'PATCH',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ status: newStatus }})
      }});
      if (!resp.ok) alert('Failed to update status');
    }}

    async function triggerPipeline() {{
      const btn = event.target;
      btn.textContent = '⏳ Running…';
      btn.disabled = true;
      await fetch('/pipeline/run', {{ method: 'POST' }});
      setTimeout(() => {{ btn.textContent = '▶ Run Pipeline Now'; btn.disabled = false; }}, 3000);
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
