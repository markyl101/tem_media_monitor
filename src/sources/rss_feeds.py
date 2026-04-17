"""Fetch and parse RSS feeds from competitors, industry, and regulatory sources."""

import logging
from datetime import datetime, timezone

import feedparser

logger = logging.getLogger(__name__)


def _parse_feed(feed_url: str, feed_name: str, category: str) -> list[dict]:
    """Parse a single RSS feed and return structured items."""
    items = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:15]:  # Cap per feed to avoid noise
            items.append(
                {
                    "url": entry.get("link", ""),
                    "title": entry.get("title", ""),
                    "snippet": entry.get("summary", "")[:500],
                    "source": feed_name,
                    "published": entry.get("published", ""),
                    "fetched_via": f"rss_{category}",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    except Exception as e:
        logger.warning(f"RSS fetch failed for {feed_name} ({feed_url}): {e}")
    return items


def fetch(cfg: dict) -> list[dict]:
    """Fetch all configured RSS feeds."""
    all_items = []
    feeds_config = cfg.get("rss_feeds", {})

    for category, feeds in feeds_config.items():
        for feed_info in feeds:
            items = _parse_feed(feed_info["url"], feed_info["name"], category)
            all_items.extend(items)
            logger.info(f"  {feed_info['name']}: {len(items)} items")

    logger.info(f"RSS feeds returned {len(all_items)} items")
    return all_items
