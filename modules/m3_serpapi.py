"""SerpApi local-news discovery module — Archetype: bluecollar (Covid pivot stories).

discover() returns raw leads with ``_content`` set to the full article text.
Scoring is handled by the shared ``scoring.claude_scorer`` module (Session 3).
"""

import itertools
import logging
import time
from typing import Optional

import requests
from newspaper import Article

from config.settings import (
    CITIES,
    DATE_WINDOWS,
    QUERY_TERMS,
    SERPAPI_KEY,
    SERPAPI_SLEEP_SECONDS,
)

logger = logging.getLogger(__name__)

# True = 5 cities × 6 windows × 3 queries = 90 calls (SerpApi free tier)
# False = 8 cities × 6 windows × 6 queries = 288 calls (Basic plan required)
REDUCED_MATRIX = True

_SERPAPI_URL = "https://serpapi.com/search"


def _build_matrix() -> list[tuple]:
    cities = CITIES[:5] if REDUCED_MATRIX else CITIES
    queries = QUERY_TERMS[:3] if REDUCED_MATRIX else QUERY_TERMS
    return list(itertools.product(cities, DATE_WINDOWS, queries))


def _serpapi_search(
    city: str,
    sites: list[str],
    cd_min: str,
    cd_max: str,
    query: str,
) -> list[dict]:
    site_filter = " OR ".join(f"site:{s}" for s in sites)
    params = {
        "engine": "google",
        "q": f"{query} ({site_filter})",
        "location": city,
        "gl": "us",
        "hl": "en",
        "as_qdr": "custom",
        "tbs": f"cdr:1,cd_min:{cd_min},cd_max:{cd_max}",
        "num": 10,
        "api_key": SERPAPI_KEY,
    }
    resp = requests.get(_SERPAPI_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("organic_results", [])


def _fetch_article(url: str) -> tuple[str, list[str]]:
    """Download and parse article text. Returns (text, authors) or ("", []) on failure."""
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text, article.authors
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return "", []


def _build_lead(
    result: dict,
    article_text: str,
    authors: list[str],
    city_label: str,
    window_label: str,
) -> dict:
    return {
        "Archetype": "bluecollar",
        "Source": "serpapi",
        "Source URL": result.get("link", ""),
        "City": city_label,
        "Date Window": window_label,
        "Status": "New",
        # Full article text for the scorer; stripped by Airtable upsert automatically.
        "_content": article_text,
        "_authors": authors,
    }


def discover(reduced: Optional[bool] = None) -> list[dict]:
    """Run the SerpApi city/date/query matrix and return raw leads.

    Args:
        reduced: True = 90-call free-tier matrix; False = 288-call full matrix.
                 Defaults to the module-level REDUCED_MATRIX flag.

    Returns:
        All unique leads with ``_content`` set. Scoring and threshold filtering
        are handled downstream by ``scoring.claude_scorer`` and the orchestrator.
    """
    global REDUCED_MATRIX
    if reduced is not None:
        REDUCED_MATRIX = reduced

    matrix = _build_matrix()
    logger.info("SerpApi matrix: %d cells (reduced=%s)", len(matrix), REDUCED_MATRIX)

    seen_urls: set[str] = set()
    leads: list[dict] = []

    for i, ((city, sites), (cd_min, cd_max, window_label), query) in enumerate(matrix):
        city_short = city.split(",")[0]
        logger.info(
            "[%d/%d] %s / %s / %.40s...",
            i + 1,
            len(matrix),
            city_short,
            window_label,
            query,
        )

        try:
            results = _serpapi_search(city, sites, cd_min, cd_max, query)
        except requests.HTTPError as exc:
            logger.error("SerpApi call failed: %s", exc)
            time.sleep(SERPAPI_SLEEP_SECONDS)
            continue

        for result in results:
            url = result.get("link", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            article_text, authors = _fetch_article(url)
            if not article_text:
                continue

            lead = _build_lead(result, article_text, authors, city_short, window_label)
            leads.append(lead)
            logger.debug("Queued %s", url)

        time.sleep(SERPAPI_SLEEP_SECONDS)

    logger.info(
        "Discovery complete: %d leads queued from %d unique URLs scanned",
        len(leads),
        len(seen_urls),
    )
    return leads


if __name__ == "__main__":
    from modules.runner import run

    run(lambda: discover(reduced=True), detail_field="City", detail_width=15)
