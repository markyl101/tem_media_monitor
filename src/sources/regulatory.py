"""Fetch regulatory updates from Ofgem, Elexon, and white paper / consultation sources.

This module covers:
- Ofgem decisions, consultations, and publications
- Elexon BSC changes and market notices
- Government / DESNZ energy white papers and consultations
"""

import logging
from datetime import datetime, timezone

import feedparser
import requests

logger = logging.getLogger(__name__)

# Additional regulatory / white paper sources beyond what's in RSS config
GOV_UK_ENERGY_FEED = (
    "https://www.gov.uk/search/policy-papers-and-consultations.atom"
    "?organisations%5B%5D=department-for-energy-security-and-net-zero"
)

OFGEM_CONSULTATIONS = "https://www.ofgem.gov.uk/consultations/rss"


def _fetch_gov_publications() -> list[dict]:
    """Fetch energy policy papers and consultations from GOV.UK."""
    items = []
    try:
        feed = feedparser.parse(GOV_UK_ENERGY_FEED)
        for entry in feed.entries[:10]:
            items.append(
                {
                    "url": entry.get("link", ""),
                    "title": entry.get("title", ""),
                    "snippet": entry.get("summary", "")[:500],
                    "source": "GOV.UK / DESNZ",
                    "published": entry.get("published", entry.get("updated", "")),
                    "fetched_via": "regulatory_gov",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    except Exception as e:
        logger.warning(f"GOV.UK feed fetch failed: {e}")
    return items


def _fetch_ofgem_consultations() -> list[dict]:
    """Fetch Ofgem consultations feed (separate from main Ofgem RSS)."""
    items = []
    try:
        feed = feedparser.parse(OFGEM_CONSULTATIONS)
        for entry in feed.entries[:10]:
            items.append(
                {
                    "url": entry.get("link", ""),
                    "title": entry.get("title", ""),
                    "snippet": entry.get("summary", "")[:500],
                    "source": "Ofgem Consultations",
                    "published": entry.get("published", ""),
                    "fetched_via": "regulatory_ofgem",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    except Exception as e:
        logger.warning(f"Ofgem consultations feed failed: {e}")
    return items


def _fetch_elexon_circulars() -> list[dict]:
    """Fetch Elexon market circulars page (HTML scrape fallback)."""
    items = []
    try:
        resp = requests.get(
            "https://www.elexon.co.uk/wp-json/wp/v2/posts",
            params={"per_page": 10, "categories": ""},  # Adjust category ID as needed
            timeout=15,
        )
        resp.raise_for_status()
        for post in resp.json():
            items.append(
                {
                    "url": post.get("link", ""),
                    "title": post.get("title", {}).get("rendered", ""),
                    "snippet": post.get("excerpt", {}).get("rendered", "")[:500],
                    "source": "Elexon",
                    "published": post.get("date", ""),
                    "fetched_via": "regulatory_elexon",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    except Exception as e:
        logger.warning(f"Elexon API fetch failed: {e}")
    return items


def fetch(cfg: dict) -> list[dict]:
    """Fetch all regulatory and white paper sources."""
    all_items = []

    all_items.extend(_fetch_gov_publications())
    all_items.extend(_fetch_ofgem_consultations())
    all_items.extend(_fetch_elexon_circulars())

    logger.info(f"Regulatory sources returned {len(all_items)} items")
    return all_items
