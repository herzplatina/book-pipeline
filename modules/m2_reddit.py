"""Reddit discovery module — Archetypes: driver, criminal, health, bluecollar.

Uses Arctic Shift (https://arctic-shift.photon-reddit.com) to search historical
Reddit posts from 2020–2023. No Reddit credentials required.

discover() returns raw leads with _content set to post title + selftext.
Scoring is handled downstream by scoring.claude_scorer.
All Reddit leads route through the human review queue (sensitivity rule).
"""

import argparse
import logging
import time

import requests

from config.settings import (
    ARCTIC_SHIFT_DATE_RANGE,
    REDDIT_FILTERS,
    REDDIT_KEYWORDS,
    REDDIT_SLEEP_SECONDS,
    SUBREDDITS,
)

logger = logging.getLogger(__name__)

_ARCTIC_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
_REDDIT_BASE = "https://www.reddit.com"

# Limit Arctic Shift keyword calls per subreddit to avoid quota exhaustion.
_ARCTIC_MAX_KEYWORDS = 3


def _build_lead(
    post_id: str,
    title: str,
    selftext: str,
    author: str,
    permalink: str,
    archetype: str,
    subreddit: str,
) -> dict:
    content = f"{title}\n\n{selftext}".strip()
    url = f"{_REDDIT_BASE}{permalink}" if permalink.startswith("/") else permalink
    return {
        "Archetype": archetype,
        "Source": "reddit",
        "Source URL": url,
        "Status": "New",
        "Reddit Username": author,
        "Subreddit": subreddit,
        "_content": content,
        "_post_id": post_id,
    }


def _arctic_fetch(subreddit: str, keyword: str, archetype: str) -> list[dict]:
    """Search Arctic Shift for historical posts matching keyword in date range."""
    leads = []
    try:
        resp = requests.get(
            _ARCTIC_URL,
            params={
                "subreddit": subreddit,
                "query": keyword,
                "after": ARCTIC_SHIFT_DATE_RANGE["after"],
                "before": ARCTIC_SHIFT_DATE_RANGE["before"],
                "limit": REDDIT_FILTERS["limit"],
                "sort": "desc",
            },
            timeout=20,
        )
        resp.raise_for_status()
        for item in resp.json().get("data", []):
            if item.get("score", 0) < REDDIT_FILTERS["min_score"]:
                continue
            permalink = item.get("permalink", "")
            leads.append(
                _build_lead(
                    post_id=item.get("id", ""),
                    title=item.get("title", ""),
                    selftext=item.get("selftext", ""),
                    author=item.get("author", "[deleted]"),
                    permalink=permalink,
                    archetype=archetype,
                    subreddit=subreddit,
                )
            )
    except requests.RequestException as exc:
        logger.warning(
            "Arctic Shift fetch failed for r/%s / %s: %s", subreddit, keyword, exc
        )
    return leads


def discover() -> list[dict]:
    """Run Arctic Shift historical search and return deduplicated raw leads.

    Returns:
        All unique leads with ``_content`` set. Scoring and threshold filtering
        are handled downstream by ``scoring.claude_scorer`` and the orchestrator.
    """
    seen_ids: set[str] = set()
    leads: list[dict] = []

    keywords = REDDIT_KEYWORDS[:_ARCTIC_MAX_KEYWORDS]
    for archetype, subreddits in SUBREDDITS.items():
        for subreddit in subreddits:
            for keyword in keywords:
                logger.info(
                    "Arctic Shift: r/%s / %.40s... (%s)", subreddit, keyword, archetype
                )
                for lead in _arctic_fetch(subreddit, keyword, archetype):
                    post_id = lead["_post_id"]
                    if post_id and post_id not in seen_ids:
                        seen_ids.add(post_id)
                        leads.append(lead)
                time.sleep(REDDIT_SLEEP_SECONDS)

    logger.info(
        "Discovery complete: %d leads from %d unique posts scanned",
        len(leads),
        len(seen_ids),
    )
    return leads


_SMOKE_REQUIRED_KEYS = {
    "Archetype",
    "Source",
    "Source URL",
    "Status",
    "Reddit Username",
    "Subreddit",
    "_content",
    "_post_id",
}


def run_smoke_test() -> dict:
    """Fetch a small live sample from Arctic Shift and validate lead structure.

    Makes a real API call. No credentials required.
    Run with: python -m modules.m2_reddit --smoke-test
    """
    _SMOKE_SUBREDDIT = "UberDrivers"
    _SMOKE_ARCHETYPE = "driver"
    _SMOKE_KEYWORD = REDDIT_KEYWORDS[0]

    leads = _arctic_fetch(_SMOKE_SUBREDDIT, _SMOKE_KEYWORD, _SMOKE_ARCHETYPE)

    for lead in leads:
        missing = _SMOKE_REQUIRED_KEYS - set(lead.keys())
        if missing:
            raise RuntimeError(f"Lead missing required keys: {missing}; lead={lead!r}")

    result = {
        "arctic_leads": len(leads),
        "subreddit": _SMOKE_SUBREDDIT,
        "keyword": _SMOKE_KEYWORD,
    }
    logger.info("Reddit smoke test complete: %s", result)
    return result


if __name__ == "__main__":
    from modules.runner import run

    _parser = argparse.ArgumentParser(
        description="Reddit discovery module (Arctic Shift)."
    )
    _parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Fetch a small live sample from Arctic Shift and validate lead structure.",
    )
    _args = _parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if _args.smoke_test:
        _result = run_smoke_test()
        print("=== Reddit Smoke Test (Arctic Shift) ===")
        for _key, _val in _result.items():
            print(f"{_key}: {_val}")
    else:
        run(discover, id_field="Reddit Username", id_width=20)
