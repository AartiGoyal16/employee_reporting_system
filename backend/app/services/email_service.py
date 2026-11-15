"""
Email Service — smtplib-based, zero extra dependencies.
Falls back gracefully to log-only mode when SMTP vars are not configured.
"""
import logging
import smtplib
import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)


def _build_html(subject: str, body_html: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg.attach(MIMEText(body_html, "html"))
    return msg


def _send_sync(to_email: str, msg: MIMEMultipart) -> bool:
    """Blocking SMTP send — called in a thread pool so it won't block the event loop."""
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    user = settings.SMTP_USER
    password = settings.SMTP_PASSWORD

    if not host or not user:
        logger.info(
            f"[EMAIL — log-only] SMTP not configured. Would send '{msg['Subject']}' to {to_email}"
        )
        return False

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.ehlo()
            if port != 465:
                server.starttls()
                server.ehlo()
            if password:
                server.login(user, password)
            msg["To"] = to_email
            server.sendmail(settings.EMAIL_FROM, to_email, msg.as_string())
        logger.info(f"[EMAIL ✓] Sent '{msg['Subject']}' → {to_email}")
        return True
    except Exception as exc:
        logger.warning(f"[EMAIL ✗] Failed to send '{msg['Subject']}' to {to_email}: {exc}")
        return False


async def send_email_async(to_email: str, subject: str, body_html: str) -> bool:
    """Non-blocking wrapper — runs the blocking SMTP call in a thread pool."""
    msg = _build_html(subject, body_html)
    return await asyncio.to_thread(_send_sync, to_email, msg)


# ---------------------------------------------------------------------------
# Email Templates
# ---------------------------------------------------------------------------

async def send_manager_notification_email(
    manager_email: str,
    manager_name: str,
    employee_name: str,
    week_start: str,
    week_end: str,
    ai_highlights: list,
    report_id: str,
) -> bool:
    """Email the manager when an employee submits their weekly report."""
    highlights_html = "".join(
        f"<li style='margin:4px 0;'>{h}</li>" for h in (ai_highlights or ["No highlights available"])
    )
    body = f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:600px;margin:auto;background:#f8fafc;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
      <div style="background:linear-gradient(135deg,#4f46e5,#2563eb);padding:28px 32px;">
        <h1 style="color:#fff;margin:0;font-size:20px;font-weight:700;">📋 Weekly Report Submitted</h1>
        <p style="color:#c7d2fe;margin:6px 0 0;font-size:14px;">Employee Reporting System</p>
      </div>
      <div style="padding:28px 32px;">
        <p style="color:#374151;font-size:15px;margin:0 0 16px;">Hi <strong>{manager_name}</strong>,</p>
        <p style="color:#374151;font-size:14px;margin:0 0 20px;">
          <strong>{employee_name}</strong> has submitted their weekly report for
          <strong>{week_start} → {week_end}</strong>.
        </p>
        <div style="background:#eff6ff;border-left:4px solid #3b82f6;border-radius:6px;padding:16px 20px;margin-bottom:20px;">
          <p style="margin:0 0 8px;font-weight:600;color:#1e40af;font-size:13px;">AI-Generated Key Highlights</p>
          <ul style="margin:0;padding-left:18px;color:#1e3a5f;font-size:13px;line-height:1.6;">
            {highlights_html}
          </ul>
        </div>
        <p style="color:#6b7280;font-size:13px;margin:0 0 20px;">
          Log in to the Employee Reporting System to view the full report and AI executive summary.
        </p>
        <p style="color:#9ca3af;font-size:12px;border-top:1px solid #e5e7eb;padding-top:16px;margin:0;">
          This is an automated notification from the Employee Reporting System.
        </p>
      </div>
    </div>
    """
    return await send_email_async(
        manager_email,
        f"[Report Submitted] {employee_name} — Week of {week_start}",
        body,
    )


async def send_reminder_email(
    employee_email: str,
    employee_name: str,
    week_end: str,
) -> bool:
    """Remind an employee to submit their weekly report before the deadline."""
    body = f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:600px;margin:auto;background:#f8fafc;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
      <div style="background:linear-gradient(135deg,#f59e0b,#d97706);padding:28px 32px;">
        <h1 style="color:#fff;margin:0;font-size:20px;font-weight:700;">⏰ Weekly Report Reminder</h1>
        <p style="color:#fef3c7;margin:6px 0 0;font-size:14px;">Submission deadline approaching</p>
      </div>
      <div style="padding:28px 32px;">
        <p style="color:#374151;font-size:15px;margin:0 0 16px;">Hi <strong>{employee_name}</strong>,</p>
        <p style="color:#374151;font-size:14px;margin:0 0 16px;">
          A friendly reminder that your weekly report is due by <strong>{week_end}</strong>.
        </p>
        <p style="color:#374151;font-size:14px;margin:0 0 20px;">
          Please log in and submit your report so your manager can review your progress.
        </p>
        <div style="background:#fffbeb;border-left:4px solid #f59e0b;border-radius:6px;padding:14px 18px;margin-bottom:20px;">
          <p style="margin:0;font-size:13px;color:#92400e;">
            💡 <strong>Tip:</strong> You can save a draft at any time and submit when ready.
          </p>
        </div>
        <p style="color:#9ca3af;font-size:12px;border-top:1px solid #e5e7eb;padding-top:16px;margin:0;">
          This is an automated reminder from the Employee Reporting System.
        </p>
      </div>
    </div>
    """
    return await send_email_async(
        employee_email,
        f"[Reminder] Submit your weekly report by {week_end}",
        body,
    )
