"""Reddit discovery module — Archetypes: driver, criminal, health, bluecollar.

Two complementary passes:
  1. PRAW         — live API: top posts per subreddit, filtered locally by keyword.
  2. Arctic Shift — historical search (2020–2023) for Covid-era stories.

discover() returns raw leads with _content set to post title + selftext.
Scoring is handled downstream by scoring.claude_scorer.
All Reddit leads route through the human review queue (sensitivity rule).
"""

import logging
import time

import praw
import requests

from config.settings import (
    ARCTIC_SHIFT_DATE_RANGE,
    REDDIT_FILTERS,
    REDDIT_KEYWORDS,
    REDDIT_SLEEP_SECONDS,
    SUBREDDITS,
    require_env,
)

logger = logging.getLogger(__name__)

_ARCTIC_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
_REDDIT_BASE = "https://www.reddit.com"

# Limit Arctic Shift keyword calls per subreddit to avoid quota exhaustion.
_ARCTIC_MAX_KEYWORDS = 3


def _praw_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=require_env("REDDIT_CLIENT_ID"),
        client_secret=require_env("REDDIT_CLIENT_SECRET"),
        user_agent=require_env("REDDIT_USER_AGENT"),
        check_for_async=False,
    )


def _keyword_match(text: str) -> bool:
    """Return True if any discovery keyword appears in the lowercased text."""
    lowered = text.lower()
    return any(kw in lowered for kw in REDDIT_KEYWORDS)


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
        "_content": content,
        "_post_id": post_id,
        "_reddit_author": author,
        "_subreddit": subreddit,
    }


def _praw_fetch(reddit: praw.Reddit, subreddit: str, archetype: str) -> list[dict]:
    """Fetch top posts from a subreddit via PRAW and filter by keyword + score."""
    leads = []
    try:
        sub = reddit.subreddit(subreddit)
        posts = sub.top(
            time_filter=REDDIT_FILTERS["time_filter"],
            limit=REDDIT_FILTERS["limit"],
        )
        for post in posts:
            if post.score < REDDIT_FILTERS["min_score"]:
                continue
            combined = f"{post.title} {post.selftext}"
            if not _keyword_match(combined):
                continue
            author = str(post.author) if post.author else "[deleted]"
            leads.append(
                _build_lead(
                    post_id=post.id,
                    title=post.title,
                    selftext=post.selftext,
                    author=author,
                    permalink=post.permalink,
                    archetype=archetype,
                    subreddit=subreddit,
                )
            )
    except Exception:
        logger.exception("PRAW fetch failed for subreddit=%s", subreddit)
    return leads


def _arctic_fetch(subreddit: str, keyword: str, archetype: str) -> list[dict]:
    """Search Arctic Shift for historical posts matching keyword in date range."""
    leads = []
    try:
        resp = requests.get(
            _ARCTIC_URL,
            params={
                "subreddit": subreddit,
                "q": keyword,
                "after": ARCTIC_SHIFT_DATE_RANGE["after"],
                "before": ARCTIC_SHIFT_DATE_RANGE["before"],
                "limit": REDDIT_FILTERS["limit"],
                "sort": "score",
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
    """Run both PRAW and Arctic Shift passes and return deduplicated raw leads.

    Returns:
        All unique leads with ``_content`` set. Scoring and threshold filtering
        are handled downstream by ``scoring.claude_scorer`` and the orchestrator.
    """
    reddit = _praw_client()
    seen_ids: set[str] = set()
    leads: list[dict] = []

    # Pass 1: PRAW (recent posts)
    for archetype, subreddits in SUBREDDITS.items():
        for subreddit in subreddits:
            logger.info("PRAW: r/%s (%s)", subreddit, archetype)
            for lead in _praw_fetch(reddit, subreddit, archetype):
                post_id = lead["_post_id"]
                if post_id and post_id not in seen_ids:
                    seen_ids.add(post_id)
                    leads.append(lead)
            time.sleep(REDDIT_SLEEP_SECONDS)

    # Pass 2: Arctic Shift (historical 2020–2023)
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


if __name__ == "__main__":
    from modules.runner import run

    run(discover, id_field="_reddit_author", id_width=20)
