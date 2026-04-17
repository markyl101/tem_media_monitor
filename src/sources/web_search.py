"""Fetch news articles via Google News RSS (no API key needed)."""

import logging
from datetime import datetime, timezone
from urllib.parse import quote

import feedparser

from src.config import search_queries

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


def fetch(cfg: dict) -> list[dict]:
    """Run all web search queries and return combined results."""
    queries = search_queries(cfg)
    all_items = []

    for query in queries:
        try:
            url = f"{GOOGLE_NEWS_RSS}?q={quote(query)}&hl=en-GB&gl=GB&ceid=GB:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                all_items.append(
                    {
                        "url": entry.get("link", ""),
                        "title": entry.get("title", ""),
                        "snippet": entry.get("summary", ""),
                        "source": entry.get("source", {}).get("title", "Google News"),
                        "published": entry.get("published", ""),
                        "fetched_via": "google_news",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
        except Exception as e:
            logger.warning(f"Google News fetch failed for '{query}': {e}")

    logger.info(f"Web search returned {len(all_items)} items across {len(queries)} queries")
    return all_items
