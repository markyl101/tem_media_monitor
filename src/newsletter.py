"""Generate and send a weekly newsletter via Gmail SMTP.

Reads the weekly log, renders a static HTML template, then sends to
configured recipients.

Requires env vars:
- GMAIL_ADDRESS: sender email
- GMAIL_APP_PASSWORD: Gmail app password (not regular password)
- NEWSLETTER_RECIPIENTS: comma-separated recipient emails
"""

import json
import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from src.config import WEEKLY_LOG_PATH, load_config

logger = logging.getLogger(__name__)

# Section order and display labels
_SECTIONS = [
    ("brand_mention", "Brand Mentions"),
    ("regulatory",    "Regulatory"),
    ("competitor",    "Competitor"),
    ("industry",      "Industry"),
    ("white_paper",   "White Papers"),
]

# Left-border colour by score
def _score_colour(score: int) -> str:
    if score >= 8:
        return "#c0392b"
    if score >= 5:
        return "#e67e22"
    return "#bdc3c7"

# Sentiment pill colour
_SENTIMENT_COLOUR = {
    "positive": "#27ae60",
    "negative": "#c0392b",
    "neutral":  "#7f8c8d",
}


def _render_item(item: dict) -> str:
    title   = escape(item.get("title", "Untitled"))
    url     = escape(item.get("url", "#"))
    source  = escape(item.get("source", ""))
    score   = item.get("relevance_score", 0)
    senti   = item.get("sentiment", "neutral")
    summary = escape(item.get("ai_summary", ""))

    border_col  = _score_colour(score)
    senti_col   = _SENTIMENT_COLOUR.get(senti, "#7f8c8d")

    return f"""
    <div style="margin-bottom:18px;">
      <a href="{url}" style="color:#0f3460; font-weight:600; font-size:15px; text-decoration:none;">{title}</a>
      {f'<p style="margin:6px 0 0; font-size:14px; color:#333; line-height:1.5;">{summary}</p>' if summary else ''}
    </div>"""


def _render_section(label: str, items: list[dict]) -> str:
    if not items:
        return ""
    rows = "".join(_render_item(i) for i in items)
    return f"""
  <div style="margin-bottom:28px;">
    <h2 style="color:#16213e; font-size:16px; font-weight:700; margin:0 0 14px;
               border-bottom:2px solid #16213e; padding-bottom:6px;">{label}</h2>
    {rows}
  </div>"""


def load_weekly_log() -> list[dict]:
    try:
        with open(WEEKLY_LOG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_weekly_log(items: list[dict]) -> None:
    with open(WEEKLY_LOG_PATH, "w") as f:
        json.dump(items, f, indent=2)


def append_to_weekly_log(items: list[dict]) -> None:
    log = load_weekly_log()
    log.extend(items)
    save_weekly_log(log)


def _get_week_items() -> list[dict]:
    """Get items from the past 7 days, then clear the log."""
    items = load_weekly_log()
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # Filter to items with score >= 4 (skip noise)
    week_items = [
        item for item in items if item.get("relevance_score", 0) >= 4
    ]

    # Sort by score descending
    week_items.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    # Clear the log
    save_weekly_log([])

    return week_items


def generate_newsletter_html(items: list[dict]) -> str:
    """Render a static HTML newsletter from scored items."""
    date_str = datetime.now(timezone.utc).strftime("%d %B %Y")

    # Group by category
    by_cat: dict[str, list[dict]] = {key: [] for key, _ in _SECTIONS}
    for item in items:
        cat = item.get("category", "industry")
        if cat in by_cat:
            by_cat[cat].append(item)

    sections_html = "".join(
        _render_section(label, by_cat[key]) for key, label in _SECTIONS
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0; padding:0; background:#e9e9e9; font-family:Arial,sans-serif;">
  <div style="max-width:600px; margin:24px auto; background:#fff; border-radius:4px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.12);">

    <!-- Header -->
    <div style="background:#ff4011; padding:24px; text-align:center;">
      <div style="color:#fff; font-size:22px; font-weight:700; letter-spacing:1px;">tem intel</div>
      <div style="color:#fff; font-size:13px; margin-top:4px;">Weekly Briefing &mdash; {date_str}</div>
    </div>

    <!-- Body -->
    <div style="padding:24px;">
      {sections_html if sections_html.strip() else '<p style="color:#999; font-size:14px;">No items to report this week.</p>'}
    </div>

    <!-- Footer -->
    <div style="background:#f5f5f5; border-top:1px solid #e0e0e0; padding:14px 24px; font-size:11px; color:#999; text-align:center;">
      tem media monitor &nbsp;&middot;&nbsp; auto-generated {date_str}
    </div>

  </div>
</body>
</html>"""


def send_newsletter(html: str, subject: str) -> None:
    """Send the newsletter via Gmail SMTP."""
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    recipients_str = os.environ.get("NEWSLETTER_RECIPIENTS", "")

    if not all([sender, password, recipients_str]):
        raise ValueError("Gmail credentials or recipients not configured")

    recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"tem intel <{sender}>"
    msg["To"] = ", ".join(recipients)

    # Plain text fallback
    plain = "This newsletter is best viewed in an HTML-capable email client."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())

    logger.info(f"Newsletter sent to {len(recipients)} recipients")


def run_newsletter() -> None:
    """Full newsletter pipeline: gather items → generate → send."""
    cfg = load_config()
    items = _get_week_items()

    if not items:
        logger.info("No items for newsletter this week — skipping")
        return

    logger.info(f"Generating newsletter from {len(items)} items")
    html = generate_newsletter_html(items)

    date_str = datetime.now(timezone.utc).strftime("%d %b %Y")
    prefix = cfg.get("newsletter", {}).get("subject_prefix", "[tem intel]")
    subject = f"{prefix} Weekly Briefing — {date_str}"

    send_newsletter(html, subject)
    logger.info("Weekly newsletter complete")
