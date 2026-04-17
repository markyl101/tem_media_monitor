"""Send alerts and digests to Slack channels.

Uses Slack Web API via slack-sdk. Requires SLACK_BOT_TOKEN env var.
"""

import json
import logging
import os
from datetime import datetime, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.config import DIGEST_QUEUE_PATH

logger = logging.getLogger(__name__)

# Emoji map for categories
CATEGORY_EMOJI = {
    "brand_mention": ":mega:",
    "competitor": ":eyes:",
    "regulatory": ":classical_building:",
    "industry": ":newspaper:",
    "white_paper": ":page_facing_up:",
}

SENTIMENT_EMOJI = {
    "positive": ":large_green_circle:",
    "neutral": ":white_circle:",
    "negative": ":red_circle:",
}


def _get_client() -> WebClient:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise ValueError("SLACK_BOT_TOKEN not set")
    return WebClient(token=token)


def send_instant_alert(item: dict, channel: str) -> None:
    """Send an instant alert for a high-score item (8-10)."""
    client = _get_client()
    score = item.get("relevance_score", 0)
    category = item.get("category", "industry")
    sentiment = item.get("sentiment", "neutral")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":rotating_light: Alert",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*<{item.get('url', '')}|{item.get('title', 'No title')}>*",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f">{item.get('ai_summary', 'No summary available')}",
            },
        },
        {"type": "divider"},
    ]

    try:
        client.chat_postMessage(channel=channel, blocks=blocks, text=f"Alert: {item.get('title', '')}")
        logger.info(f"Sent instant alert to {channel}: {item.get('title', '')[:60]}")
    except SlackApiError as e:
        logger.error(f"Slack alert failed: {e.response['error']}")


def send_daily_digest(items: list[dict], channel: str) -> None:
    """Post the daily digest — items grouped by category."""
    if not items:
        logger.info("No digest items to send")
        return

    client = _get_client()

    # Group by category
    by_category: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("category", "industry")
        by_category.setdefault(cat, []).append(item)

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":sunrise: Morning Intel Digest — {datetime.now(timezone.utc).strftime('%d %b %Y')}",
            },
        },
        {"type": "divider"},
    ]

    # Order categories by priority
    category_order = ["brand_mention", "competitor", "regulatory", "white_paper", "industry"]
    for cat in category_order:
        cat_items = by_category.get(cat, [])
        if not cat_items:
            continue

        emoji = CATEGORY_EMOJI.get(cat, ":grey_question:")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *{cat.replace('_', ' ').title()}*",
                },
            }
        )

        for item in sorted(cat_items, key=lambda x: x.get("relevance_score", 0), reverse=True):
            score = item.get("relevance_score", 0)
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"• *<{item.get('url', '')}|{item.get('title', 'No title')}>*\n"
                            f"  _{item.get('ai_summary', '')}_"
                        ),
                    },
                }
            )

        blocks.append({"type": "divider"})

    # Slack has a 50-block limit — truncate if needed
    if len(blocks) > 49:
        blocks = blocks[:48]
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_...truncated. See full log in repo._"},
            }
        )

    try:
        client.chat_postMessage(channel=channel, blocks=blocks, text="Morning Intel Digest")
        logger.info(f"Sent daily digest to {channel} ({len(items)} items)")
    except SlackApiError as e:
        logger.error(f"Slack digest failed: {e.response['error']}")


# --- Digest queue management ---


def load_digest_queue() -> list[dict]:
    try:
        with open(DIGEST_QUEUE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_digest_queue(items: list[dict]) -> None:
    with open(DIGEST_QUEUE_PATH, "w") as f:
        json.dump(items, f, indent=2)


def add_to_digest_queue(items: list[dict]) -> None:
    queue = load_digest_queue()
    queue.extend(items)
    save_digest_queue(queue)
    logger.info(f"Added {len(items)} items to digest queue (total: {len(queue)})")


def flush_digest_queue() -> list[dict]:
    """Return all queued items and clear the queue."""
    items = load_digest_queue()
    save_digest_queue([])
    return items
