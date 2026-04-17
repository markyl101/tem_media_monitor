"""Load and expose configuration."""

import os
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.yml"
DATA_DIR = ROOT_DIR / "data"

SEEN_URLS_PATH = DATA_DIR / "seen_urls.json"
DIGEST_QUEUE_PATH = DATA_DIR / "digest_queue.json"
WEEKLY_LOG_PATH = DATA_DIR / "weekly_log.json"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def all_keywords(cfg: dict) -> list[str]:
    """Flatten all keyword buckets into a single list."""
    kw = cfg["keywords"]
    return kw["brand"] + kw["competitors"] + kw["industry"]


def search_queries(cfg: dict) -> list[str]:
    """Build search queries optimised for news APIs.

    Groups keywords into OR-joined queries to reduce API calls.
    """
    kw = cfg["keywords"]
    queries = []
    # Brand terms — always search individually (exact match matters)
    for term in kw["brand"]:
        queries.append(f'"{term}"')
    # Competitors — batch into groups of 3
    comps = kw["competitors"]
    for i in range(0, len(comps), 3):
        batch = comps[i : i + 3]
        queries.append(" OR ".join(f'"{c}"' for c in batch))
    # Industry terms — one per query (they're already specific)
    for term in kw["industry"]:
        queries.append(f'"{term}"')
    return queries
