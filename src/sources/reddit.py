"""Search Reddit for keyword mentions via Apify trudax/reddit-scraper-lite.

Requires APIFY_API_TOKEN environment variable.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ACTOR_ID = "trudax/reddit-scraper-lite"


def fetch(cfg: dict) -> list[dict]:
    """Search configured Reddit community for keyword mentions via Apify."""
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        logger.info("APIFY_API_TOKEN not set — skipping Reddit source")
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("apify-client not installed — skipping Reddit source")
        return []

    reddit_cfg = cfg.get("reddit", {})
    community = reddit_cfg.get("community", "energy")
    keywords = cfg["keywords"]

    # Search brand + competitor names; industry terms are too broad for Reddit
    search_terms = keywords["brand"] + keywords["competitors"]

    all_items = []
    client = ApifyClient(token)

    def _search(term: str) -> list[dict]:
        run_input = {
            "searches": [term],
            "searchCommunityName": community,
            "sort": "new",
            "time": "week",
            "maxItems": 10,
            "maxPostCount": 10,
            "maxComments": 0,
            "skipComments": True,
            "proxy": {"useApifyProxy": True},
        }
        try:
            run = client.actor(ACTOR_ID).call(run_input=run_input)
            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                logger.warning(f"No dataset returned for search term '{term}'")
                return []

            items = []
            for item in client.dataset(dataset_id).iterate_items():
                if item.get("dataType") != "post":
                    continue
                items.append(
                    {
                        "url": item.get("url", ""),
                        "title": item.get("title", ""),
                        "snippet": (item.get("body") or "")[:500],
                        "source": item.get("communityName", f"r/{community}"),
                        "published": item.get("createdAt", datetime.now(timezone.utc).isoformat()),
                        "fetched_via": "reddit",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            return items
        except Exception as e:
            logger.warning(f"Apify Reddit search failed for '{term}': {e}")
            return []

    with ThreadPoolExecutor(max_workers=len(search_terms)) as executor:
        futures = {executor.submit(_search, term): term for term in search_terms}
        for future in as_completed(futures):
            all_items.extend(future.result())

    logger.info(f"Reddit (Apify) returned {len(all_items)} items")
    return all_items
