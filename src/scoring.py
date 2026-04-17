"""Score and classify items using Claude.

Each item gets:
- relevance_score (1-10)
- category: one of brand_mention, competitor, regulatory, industry, white_paper
- sentiment: positive, neutral, negative
- summary: 1-2 sentence summary
- reasoning: why this score
"""

import json
import logging
import os

from anthropic import Anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a media monitoring analyst for tem energy, a UK-based I&C (Industrial & Commercial) renewable energy supplier. Your job is to score and classify news items for relevance to tem's business.

About tem:
- B2B renewable energy supplier in the UK market
- Focuses on I&C customers, generators (solar, AD, wind), and flex/trading
- Competes with Yü Energy, Opus Energy, Haven Power, SmartestEnergy, Octopus Energy Business, Drax, TotalEnergies Gas & Power, F&S Energy, Evolve Energy, Fuse Energy, EDF Energy Business
- Key topics: wholesale electricity, PPAs, half-hourly/MHHS settlement, Ofgem regulation, Elexon BSC, balancing mechanism, DNO charges, BSUoS

Scoring guide:
- 10: tem named directly, or a market event big enough that we should have a response ready
- 8: Something that changes what we do or say — a competitor product launch, an Ofgem ruling that affects our pricing, trade press that prominently covers our space. Someone reads it today.
- 5: Background reading. An industry trend piece, a general article on wholesale prices. Worth knowing, no action needed this week.
- 1-3: Tangentially related or not relevant to tem's business

Categories:
- brand_mention: tem or "Renewable Energy Direct" mentioned directly
- competitor: About a named competitor
- regulatory: Ofgem, Elexon, DESNZ, BSC changes, consultations, white papers, policy
- industry: General energy industry news, market trends, wholesale prices
- white_paper: Formal publications, research papers, consultation responses

You MUST respond with valid JSON only. No markdown, no explanation outside the JSON."""

ITEM_PROMPT_TEMPLATE = """Score these items. Return a JSON array with one object per item.

Each object must have:
- "index": the item's position (0-based)
- "relevance_score": integer 1-10
- "category": one of brand_mention, competitor, regulatory, industry, white_paper
- "sentiment": positive, neutral, or negative
- "summary": 1-2 sentence summary of why this matters to tem
- "reasoning": brief explanation of the score

Items to score:
{items_json}"""


def _batch_items(items: list[dict], batch_size: int = 10) -> list[list[dict]]:
    """Split items into batches for API calls."""
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _score_batch(client: Anthropic, model: str, batch: list[dict]) -> list[dict]:
    """Score a batch of items via Claude API."""
    # Prepare minimal item representations for the prompt
    items_for_prompt = [
        {
            "index": i,
            "title": item.get("title", ""),
            "snippet": item.get("snippet", "")[:300],
            "source": item.get("source", ""),
            "url": item.get("url", ""),
        }
        for i, item in enumerate(batch)
    ]

    prompt = ITEM_PROMPT_TEMPLATE.format(items_json=json.dumps(items_for_prompt, indent=2))

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text.strip()
        # Handle potential markdown code fences
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        scores = json.loads(response_text)
        return scores

    except Exception as e:
        logger.error(f"Scoring batch failed: {e}")
        # Return neutral defaults so pipeline doesn't break
        return [
            {
                "index": i,
                "relevance_score": 5,
                "category": "industry",
                "sentiment": "neutral",
                "summary": "Scoring failed — manual review needed",
                "reasoning": f"API error: {str(e)[:100]}",
            }
            for i in range(len(batch))
        ]


def score_items(items: list[dict], cfg: dict) -> list[dict]:
    """Score all items using Claude and merge scores back into item dicts."""
    if not items:
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — cannot score items")
        return items

    client = Anthropic(api_key=api_key)
    model = cfg.get("scoring", {}).get("model", "claude-haiku-4-5-20251001")

    batches = _batch_items(items, batch_size=10)
    all_scored = []

    for batch_idx, batch in enumerate(batches):
        logger.info(f"Scoring batch {batch_idx + 1}/{len(batches)} ({len(batch)} items)")
        scores = _score_batch(client, model, batch)

        # Merge scores back into original items
        score_map = {s["index"]: s for s in scores}
        for i, item in enumerate(batch):
            score_data = score_map.get(i, {})
            item["relevance_score"] = score_data.get("relevance_score", 5)
            item["category"] = score_data.get("category", "industry")
            item["sentiment"] = score_data.get("sentiment", "neutral")
            item["ai_summary"] = score_data.get("summary", "")
            item["ai_reasoning"] = score_data.get("reasoning", "")
            all_scored.append(item)

    # Sort by score descending
    all_scored.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    logger.info(
        f"Scored {len(all_scored)} items. "
        f"High (8+): {sum(1 for i in all_scored if i.get('relevance_score', 0) >= 8)}, "
        f"Medium (4-7): {sum(1 for i in all_scored if 4 <= i.get('relevance_score', 0) <= 7)}, "
        f"Low (<4): {sum(1 for i in all_scored if i.get('relevance_score', 0) < 4)}"
    )
    return all_scored
