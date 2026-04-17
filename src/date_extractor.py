"""Attempt to extract published dates from articles with missing dates.

For items where 'published' is empty:
1. Fetch the article URL and scan for common HTML date metadata (fast, no API cost).
2. Fall back to Claude if the HTML scan finds nothing.

Items where a date is found have their 'published' field updated in-place.
Items where no date can be determined are marked with published="unknown" so
they are excluded from alerts and the daily digest.
"""

import logging
import os
import re
from typing import Optional

import requests
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Common HTML/JSON-LD patterns that carry a published date
_DATE_PATTERNS = [
    # Open Graph / article meta
    r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time["\']',
    # Generic meta name variants
    r'<meta[^>]+name=["\']pubdate["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']pubdate["\']',
    r'<meta[^>]+name=["\']date["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']date["\']',
    # JSON-LD structured data
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'"dateCreated"\s*:\s*"([^"]+)"',
    # HTML5 <time> element
    r'<time[^>]+datetime=["\']([^"\']+)["\']',
]

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; tem-media-monitor/1.0; +https://tem.energy)"
    )
}

DATE_EXTRACTION_SYSTEM = (
    "You are extracting a published date from a web article. "
    "Return ONLY a valid ISO 8601 date string (for example: 2024-01-15 or "
    "2024-01-15T10:30:00Z). If you cannot determine when the article was "
    "published, return exactly the word: unknown\n"
    "No explanation. No other text."
)


def _fetch_page_head(url: str, timeout: int = 10) -> Optional[str]:
    """Fetch a page and return the <head> section plus the first 1 000 chars of <body>."""
    try:
        resp = requests.get(url, timeout=timeout, headers=_REQUEST_HEADERS)
        resp.raise_for_status()
        html = resp.text

        head_match = re.search(r"<head[^>]*>(.*?)</head>", html, re.IGNORECASE | re.DOTALL)
        head = head_match.group(1) if head_match else ""

        body_match = re.search(r"<body[^>]*>(.*)", html, re.IGNORECASE | re.DOTALL)
        body_start = body_match.group(1)[:1000] if body_match else html[:1000]

        return head + "\n" + body_start
    except Exception as e:
        logger.debug("Could not fetch %s: %s", url, e)
        return None


def _extract_date_from_html(html_snippet: str) -> Optional[str]:
    """Try to extract a published date string from HTML using common patterns."""
    for pattern in _DATE_PATTERNS:
        match = re.search(pattern, html_snippet, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return None


def _ask_claude_for_date(
    client: Anthropic,
    model: str,
    url: str,
    title: str,
    snippet: str,
    page_content: Optional[str],
) -> Optional[str]:
    """Ask Claude to extract a published date from the article content."""
    content_section = (
        f"\n\nPage content (HTML head + body start):\n{page_content[:3000]}"
        if page_content
        else ""
    )
    prompt = (
        f"Article URL: {url}\n"
        f"Title: {title}\n"
        f"Snippet: {snippet[:300]}"
        f"{content_section}"
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=50,
            system=DATE_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.content[0].text.strip()
        if result.lower() == "unknown":
            return None
        return result
    except Exception as e:
        logger.error("Claude date extraction failed for %s: %s", url, e)
        return None


def enrich_missing_dates(items: list[dict], cfg: dict) -> list[dict]:
    """For items with an empty 'published' field, attempt to extract a date.

    Strategy (in order):
    1. Fetch the article URL and scan for common HTML date metadata.
    2. Fall back to Claude if the HTML scan finds nothing.

    Items where a date is found have their 'published' field updated.
    Items where no date can be determined are marked published="unknown"
    and will be excluded from alerts and the daily digest.
    """
    missing = [item for item in items if not item.get("published", "").strip()]
    if not missing:
        return items

    logger.info(
        "Attempting date extraction for %d item(s) with missing published dates",
        len(missing),
    )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client: Optional[Anthropic] = Anthropic(api_key=api_key) if api_key else None
    model: str = cfg.get("scoring", {}).get("model", "claude-haiku-4-5-20251001")

    for item in missing:
        url = item.get("url", "")
        if not url:
            item["published"] = "unknown"
            continue

        # Step 1: try fast HTML meta-tag extraction
        page_content = _fetch_page_head(url)
        date_str: Optional[str] = None
        if page_content:
            date_str = _extract_date_from_html(page_content)

        # Step 2: fall back to Claude
        if not date_str and client:
            date_str = _ask_claude_for_date(
                client,
                model,
                url,
                item.get("title", ""),
                item.get("snippet", ""),
                page_content,
            )

        if date_str:
            logger.info(
                "Extracted date '%s' for: %s",
                date_str,
                item.get("title", url)[:70],
            )
            item["published"] = date_str
        else:
            logger.info(
                "No date found — excluding: %s",
                item.get("title", url)[:70],
            )
            item["published"] = "unknown"

    return items
