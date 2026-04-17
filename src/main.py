"""Main pipeline orchestrator.

Usage:
    python -m src.main scan       # Hourly: fetch → dedup → score → route
    python -m src.main digest     # Daily: post digest to Slack, clear queue
    python -m src.main newsletter # Weekly: generate and email newsletter
    python -m src.main prune      # Monthly: clean old URLs from seen list
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from src.config import load_config
from src.dedup import deduplicate, prune_old
from src.newsletter import append_to_weekly_log, run_newsletter
from src.scoring import score_items
from src.slack_alerts import (
    add_to_digest_queue,
    flush_digest_queue,
    send_daily_digest,
    send_instant_alert,
)
from src.sources import rss_feeds, reddit, regulatory, web_search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _filter_by_age(items: list[dict], max_age_hours: float) -> list[dict]:
    """Drop items whose published date is older than max_age_hours.

    Items with missing or unparseable dates are kept (fail-open).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    fresh = []
    for item in items:
        pub = item.get("published", "")
        if not pub:
            fresh.append(item)
            continue
        pub_dt = None
        try:
            pub_dt = parsedate_to_datetime(pub)  # RFC 2822 (RSS / Google News)
        except Exception:
            pass
        if pub_dt is None:
            try:
                pub_dt = datetime.fromisoformat(pub)  # ISO 8601 (Reddit / internal)
            except Exception:
                pass
        if pub_dt is None:
            # Unknown format — include rather than silently drop
            fresh.append(item)
            continue
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        if pub_dt >= cutoff:
            fresh.append(item)
    return fresh


def run_scan():
    """Hourly scan pipeline."""
    cfg = load_config()
    scoring_cfg = cfg.get("scoring", {})
    slack_cfg = cfg.get("slack", {})

    # 1. Fetch from all sources
    logger.info("=== Fetching from all sources ===")
    all_items = []
    all_items.extend(web_search.fetch(cfg))
    all_items.extend(rss_feeds.fetch(cfg))
    all_items.extend(reddit.fetch(cfg))
    all_items.extend(regulatory.fetch(cfg))
    logger.info(f"Total raw items: {len(all_items)}")

    # 2a. Age filter — keep only items published in the last 2 hours
    max_age_hours = cfg.get("scan", {}).get("max_age_hours", 2)
    all_items = _filter_by_age(all_items, max_age_hours)
    logger.info(f"After age filter ({max_age_hours}h): {len(all_items)} items")

    if not all_items:
        logger.info("No recent items — exiting")
        return

    # 2. Deduplicate
    logger.info("=== Deduplicating ===")
    new_items = deduplicate(all_items)

    if not new_items:
        logger.info("No new items after dedup — exiting")
        return

    # 3. Score with Claude
    logger.info("=== Scoring with Claude ===")
    scored_items = score_items(new_items, cfg)

    # 4. Route by score
    logger.info("=== Routing ===")
    instant_min = scoring_cfg.get("instant_alert_min", 8)
    digest_min = scoring_cfg.get("digest_min", 4)
    instant_channel = slack_cfg.get("instant_channel", "#market-intel")
    digest_channel = slack_cfg.get("digest_channel", "#service-content-and-credibility")

    instant_items = []
    digest_items = []
    low_items = []

    for item in scored_items:
        score = item.get("relevance_score", 0)
        if score >= instant_min:
            instant_items.append(item)
        elif score >= digest_min:
            digest_items.append(item)
        else:
            low_items.append(item)

    logger.info(
        f"Routed: {len(instant_items)} instant, "
        f"{len(digest_items)} digest, {len(low_items)} log-only"
    )

    # 5. Send instant alerts
    for item in instant_items:
        send_instant_alert(item, instant_channel)

    # 6. Queue digest items
    if digest_items:
        add_to_digest_queue(digest_items)

    # 7. Append everything scored 4+ to weekly log (for newsletter)
    newsletter_items = instant_items + digest_items
    if newsletter_items:
        append_to_weekly_log(newsletter_items)

    logger.info("=== Scan complete ===")


def run_digest():
    """Daily digest pipeline."""
    cfg = load_config()
    slack_cfg = cfg.get("slack", {})
    digest_channel = slack_cfg.get("digest_channel", "#service-content-and-credibility")

    items = flush_digest_queue()
    if items:
        send_daily_digest(items, digest_channel)
    else:
        logger.info("Digest queue empty — nothing to send")


def run_newsletter_cmd():
    """Weekly newsletter pipeline."""
    run_newsletter()


def run_prune():
    """Prune old URLs from seen list."""
    prune_old(days=30)


def main():
    parser = argparse.ArgumentParser(description="tem media monitor")
    parser.add_argument(
        "command",
        choices=["scan", "digest", "newsletter", "prune"],
        help="Pipeline to run",
    )
    args = parser.parse_args()

    commands = {
        "scan": run_scan,
        "digest": run_digest,
        "newsletter": run_newsletter_cmd,
        "prune": run_prune,
    }

    logger.info(f"Running: {args.command}")
    commands[args.command]()


if __name__ == "__main__":
    main()
