"""
emailer.py — Sends a daily HTML digest of new high-score jobs via Gmail API.
Uses OAuth2 with a pre-obtained refresh token (no browser pop-up at runtime).
"""

from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from urllib.parse import urlsplit

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from src.settings import get_settings

logger = logging.getLogger(__name__)


def _safe_http_url(value: str) -> str:
    parts = urlsplit(value or "")
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        return "#"
    return value


def _get_gmail_service():
    client_id, client_secret, refresh_token, _, _ = (
        get_settings().require_gmail_credentials()
    )
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _score_badge(score: float) -> str:
    if score >= 0.8:
        return f'<span style="background:#22c55e;color:white;padding:2px 8px;border-radius:999px;font-size:12px;">🔥 {score:.0%}</span>'
    if score >= 0.6:
        return f'<span style="background:#f59e0b;color:white;padding:2px 8px;border-radius:999px;font-size:12px;">⭐ {score:.0%}</span>'
    return f'<span style="background:#94a3b8;color:white;padding:2px 8px;border-radius:999px;font-size:12px;">{score:.0%}</span>'


def _build_html(jobs: list[dict]) -> str:
    if not jobs:
        return "<p>No unsent high-score jobs are waiting for delivery.</p>"

    rows = ""
    for job in jobs:
        score = job.get("match_score") or 0.0
        changes = escape(str(job.get("changes_made") or "—")[:200], quote=True)
        title = escape(str(job.get("title") or ""), quote=True)
        company = escape(str(job.get("company") or ""), quote=True)
        location = escape(str(job.get("location") or "—"), quote=True)
        source = escape(str(job.get("source") or "").title(), quote=True)
        safe_url = escape(_safe_http_url(str(job.get("url") or "")), quote=True)
        rows += f"""
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;">
            <a href="{safe_url}" rel="noopener noreferrer" style="color:#3b82f6;font-weight:600;text-decoration:none;">
              {title}
            </a><br>
            <small style="color:#64748b;">{company} · {location}</small>
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;text-align:center;">
            {_score_badge(score)}
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#475569;font-size:13px;">
            {changes}…
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#64748b;">
            {source}
          </td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;margin:0;padding:24px;">
      <div style="max-width:860px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1);">
        <div style="background:#1e293b;color:white;padding:20px 24px;">
          <h2 style="margin:0;">📋 Daily Job Digest</h2>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:14px;">{len(jobs)} new matches above threshold · sorted by score</p>
        </div>
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr style="background:#f1f5f9;text-align:left;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:.05em;">
              <th style="padding:10px 16px;">Role</th>
              <th style="padding:10px 16px;text-align:center;">Score</th>
              <th style="padding:10px 16px;">CV Changes</th>
              <th style="padding:10px 16px;">Source</th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
        <div style="padding:16px 24px;color:#94a3b8;font-size:12px;">
          Dashboard → <a href="{get_settings().app_base_url.rstrip('/')}/dashboard" style="color:#3b82f6;">Open dashboard</a>
        </div>
      </div>
    </body>
    </html>
    """


def send_digest(jobs: list[dict], *, message_id: str | None = None) -> bool:
    """Send the daily digest. Returns True on success."""
    if not jobs:
        logger.info("No jobs to digest — skipping email.")
        return True

    settings = get_settings()
    _, _, _, sender_email, recipient_email = settings.require_gmail_credentials()
    html_body = _build_html(jobs)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📋 Job Digest — {len(jobs)} new match{'es' if len(jobs) != 1 else ''}"
    if message_id:
        msg["Message-ID"] = message_id
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        service = _get_gmail_service()
        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        logger.info("Digest sent to %s (%d jobs)", recipient_email, len(jobs))
        return True
    except Exception as exc:
        logger.error("Failed to send digest (%s)", type(exc).__name__)
        return False
