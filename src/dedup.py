"""Deduplicate items against previously seen URLs.

State is stored in data/seen_urls.json — a dict mapping URL → first-seen ISO timestamp.
This file is committed back to the repo after each run so state persists.
"""

import json
import logging
from datetime import datetime, timezone

from src.config import SEEN_URLS_PATH

logger = logging.getLogger(__name__)


def load_seen() -> dict[str, str]:
    """Load the seen-URLs map from disk."""
    try:
        with open(SEEN_URLS_PATH) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen(seen: dict[str, str]) -> None:
    """Write the seen-URLs map back to disk."""
    with open(SEEN_URLS_PATH, "w") as f:
        json.dump(seen, f, indent=2)


def deduplicate(items: list[dict]) -> list[dict]:
    """Remove items whose URL we've already processed.

    Returns only new items. Updates and saves the seen-URLs map.
    """
    seen = load_seen()
    new_items = []
    now = datetime.now(timezone.utc).isoformat()

    for item in items:
        url = item.get("url", "").strip()
        if not url:
            continue
        if url not in seen:
            seen[url] = now
            new_items.append(item)

    save_seen(seen)
    logger.info(f"Dedup: {len(items)} in → {len(new_items)} new ({len(items) - len(new_items)} already seen)")
    return new_items


def prune_old(days: int = 30) -> None:
    """Remove entries older than `days` to keep the file manageable."""
    seen = load_seen()
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    pruned = {
        url: ts
        for url, ts in seen.items()
        if datetime.fromisoformat(ts).timestamp() > cutoff
    }
    removed = len(seen) - len(pruned)
    save_seen(pruned)
    if removed:
        logger.info(f"Pruned {removed} URLs older than {days} days")
