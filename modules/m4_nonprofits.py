"""Nonprofits & archives discovery module — Archetypes: criminal, extremist, health, bluecollar.

Two sub-sources:
  1. Nonprofit story pages — scrape story/alumni/people pages listed in NONPROFIT_URLS.
  2. ListenNotes API     — podcast episode search using LISTENNOTES_QUERIES.

discover() returns raw leads with _content set. Scoring is handled downstream.
"""

import logging
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from newspaper import Article

from config.settings import (
    LISTENNOTES_QUERIES,
    NONPROFIT_SLEEP_SECONDS,
    NONPROFIT_URLS,
    require_env,
)

logger = logging.getLogger(__name__)

_LISTENNOTES_BASE = "https://listen-api.listennotes.com/api/v2"

# Map nonprofit domain → archetype
_DOMAIN_ARCHETYPE: dict[str, str] = {
    "defyventures.org": "criminal",
    "prisonfellowship.org": "criminal",
    "thedoefund.org": "criminal",
    "cleanslate.org": "criminal",
    "lifeafterhate.org": "extremist",
    "moonshotcve.com": "extremist",
}

# Map ListenNotes query → archetype
_QUERY_ARCHETYPE: dict[str, str] = {
    "former prisoner entrepreneur": "criminal",
    "Joe Dispenza healing story": "health",
    "Covid job loss rebuilt life": "bluecollar",
    "deradicalization story": "extremist",
    "addiction recovery second career": "health",
}

_MAX_STORY_LINKS = 50

# Path segments that indicate an individual story/person page
_STORY_PATH_SEGMENTS = (
    "/stories/",
    "/story/",
    "/alumni/",
    "/alumni-stories/",
    "/people/",
    "/our-team/",
    "/team/",
    "/profiles/",
)


def _archetype_for_url(url: str) -> str:
    domain = re.sub(r"^www\.", "", urlparse(url).netloc)
    return _DOMAIN_ARCHETYPE.get(domain, "criminal")


def _extract_story_links(base_url: str, html: str) -> list[str]:
    """Return individual story/person page URLs found in a nonprofit index page."""
    base_domain = urlparse(base_url).netloc
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        parsed = urlparse(href)
        if parsed.netloc != base_domain or href == base_url:
            continue
        path = parsed.path.lower()
        if any(seg in path for seg in _STORY_PATH_SEGMENTS):
            links.add(href.split("?")[0].split("#")[0])
    return list(links)


def _fetch_page(url: str) -> str:
    """Download raw HTML for a URL. Returns empty string on failure."""
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return resp.text
    except requests.HTTPError as exc:
        logger.warning("Page fetch failed %s: %s", url, exc)
        return ""


def _fetch_article_text(url: str) -> str:
    """Extract article text with newspaper3k. Returns empty string on failure."""
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception:
        logger.exception("Article parse failed url=%s", url)
        return ""


def _scrape_nonprofit(index_url: str) -> list[dict]:
    """Scrape an individual nonprofit story index page and its linked story pages."""
    archetype = _archetype_for_url(index_url)
    leads = []

    html = _fetch_page(index_url)
    if not html:
        return leads

    story_urls = _extract_story_links(index_url, html)[:_MAX_STORY_LINKS]
    logger.info("  Found %d story links on %s", len(story_urls), index_url)

    for url in story_urls:
        text = _fetch_article_text(url)
        if not text:
            continue
        leads.append(
            {
                "Archetype": archetype,
                "Source": "nonprofit",
                "Source URL": url,
                "Status": "New",
                "_content": text,
            }
        )
        time.sleep(NONPROFIT_SLEEP_SECONDS)

    return leads


def _listennotes_search(query: str) -> list[dict]:
    """Search ListenNotes for podcast episodes. Returns raw leads."""
    archetype = _QUERY_ARCHETYPE.get(query, "health")
    leads = []
    try:
        resp = requests.get(
            f"{_LISTENNOTES_BASE}/search",
            params={
                "q": query,
                "type": "episode",
                "sort_by_date": 0,
                "language": "English",
            },
            headers={"X-ListenAPI-Key": require_env("LISTENNOTES_KEY")},
            timeout=20,
        )
        resp.raise_for_status()
        for ep in resp.json().get("results", []):
            description = ep.get("description_original") or ep.get("description", "")
            title = ep.get("title_original") or ep.get("title", "")
            url = ep.get("listennotes_url", "")
            if not description or not url:
                continue
            leads.append(
                {
                    "Archetype": archetype,
                    "Source": "podcast",
                    "Source URL": url,
                    "Status": "New",
                    "_content": f"{title}\n\n{description}",
                    "_podcast": ep.get("podcast", {}).get("title_original", ""),
                }
            )
    except requests.HTTPError as exc:
        logger.warning("ListenNotes search failed (%s): %s", query, exc)
    return leads


def discover() -> list[dict]:
    """Scrape nonprofit story pages and search ListenNotes. Returns raw leads.

    Returns:
        All unique leads with ``_content`` set. Scoring and threshold filtering
        are handled downstream by ``scoring.claude_scorer`` and the orchestrator.
    """
    seen_urls: set[str] = set()
    leads: list[dict] = []

    # Pass 1: nonprofit story pages
    for url in NONPROFIT_URLS:
        logger.info("Scraping nonprofit: %s", url)
        for lead in _scrape_nonprofit(url):
            src = lead["Source URL"]
            if src not in seen_urls:
                seen_urls.add(src)
                leads.append(lead)
        time.sleep(NONPROFIT_SLEEP_SECONDS)

    # Pass 2: ListenNotes podcast search
    for query in LISTENNOTES_QUERIES:
        logger.info("ListenNotes: %.50s...", query)
        for lead in _listennotes_search(query):
            src = lead["Source URL"]
            if src not in seen_urls:
                seen_urls.add(src)
                leads.append(lead)
        time.sleep(NONPROFIT_SLEEP_SECONDS)

    logger.info("Discovery complete: %d leads from nonprofits + podcasts", len(leads))
    return leads


if __name__ == "__main__":
    from modules.runner import run

    run(discover)
