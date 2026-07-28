"""ListenNotes podcast discovery module.

Active source:
  - ListenNotes API episode search using LISTENNOTES_QUERIES.

discover() returns raw leads with _content set to episode title + show notes.
Scoring is handled downstream by scoring.claude_scorer.
"""

import json
import logging
import re
import time
from urllib.parse import urlparse

import anthropic
import requests
from bs4 import BeautifulSoup

from config.settings import (
    LISTENNOTES_QUERIES,
    LISTENNOTES_SLEEP_SECONDS,
    require_env,
)
from utils import _dedupe, _extract_emails, _parse_json_object

logger = logging.getLogger(__name__)

_anthropic_client: "anthropic.Anthropic | None" = None


def _get_anthropic_client() -> "anthropic.Anthropic":
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(
            api_key=require_env("ANTHROPIC_API_KEY")
        )
    return _anthropic_client


_LISTENNOTES_BASE = "https://listen-api.listennotes.com/api/v2"
_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 350
_URL_RE = re.compile(r"https?://[^\s<>)\"']+")
_NAME_RE = re.compile(
    r"\b(?:with|featuring|guest|interview with|talks with|speaks with|conversation with)\s+"
    r"([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})\b",
    re.IGNORECASE,
)
_TITLE_NAME_SUFFIX_RE = re.compile(
    r"[:\-]\s*([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})\s*$"
)
_NAME_STOP_WORDS = {
    "about",
    "and",
    "as",
    "at",
    "because",
    "but",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "over",
    "the",
    "to",
    "with",
}

_QUERY_ARCHETYPE: dict[str, str] = {
    "former prisoner entrepreneur": "criminal",
    "Joe Dispenza healing story": "health",
    "Covid job loss rebuilt life": "bluecollar",
    "deradicalization story": "extremist",
    "addiction recovery second career": "health",
}

_INTERVIEWEE_SYSTEM_PROMPT = """You extract interview guest metadata from podcast show notes.
Return ONLY a JSON object with these keys:
{
  "name": string or null,
  "first_name": string or null,
  "last_name": string or null,
  "role": string or null,
  "organization": string or null,
  "location": string or null,
  "confidence": number,
  "notes": string or null
}
Only use information explicitly present in the show notes/title. If you are unsure, use null.
Do not invent or infer unsupported facts.
"""

_IGNORED_WEBSITE_DOMAINS = {
    "listennotes.com",
    "lnns.co",
    "podcasts.apple.com",
    "spotify.com",
    "open.spotify.com",
    "youtube.com",
    "youtu.be",
}


def _clean_text(value: str) -> str:
    """Convert ListenNotes HTML-ish text to readable plain text."""
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return re.sub(r"^www\.", "", host)


def _is_candidate_website(url: str) -> bool:
    domain = _domain(url)
    if not domain or "." not in domain:
        return False
    return domain not in _IGNORED_WEBSITE_DOMAINS


def _extract_website_urls(*texts: str) -> list[str]:
    urls: list[str] = []
    for text in texts:
        if not text:
            continue
        soup = BeautifulSoup(text, "html.parser")
        urls.extend(a["href"] for a in soup.find_all("a", href=True))
        urls.extend(_URL_RE.findall(text))

    cleaned = [url.rstrip(".,;:") for url in urls]
    return _dedupe([url for url in cleaned if _is_candidate_website(url)])


def _normalize_name(name: str) -> str | None:
    pieces = [piece.strip(" ,.:;()[]{}\"'") for piece in name.split()]
    cleaned: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        if piece.lower() in _NAME_STOP_WORDS:
            break
        cleaned.append(piece)
    if len(cleaned) < 2:
        return None
    return " ".join(cleaned)


def _extract_interviewee_name(title: str, description: str) -> str | None:
    """Conservatively extract the guest/interviewee name from show notes."""
    for match in _NAME_RE.finditer(description):
        candidate = _normalize_name(match.group(1))
        if candidate:
            return candidate

    title_match = _TITLE_NAME_SUFFIX_RE.search(title)
    if title_match:
        candidate = _normalize_name(title_match.group(1))
        if candidate:
            return candidate

    return None


def _extract_interviewee_profile(
    title: str,
    description: str,
    podcast_name: str,
) -> dict:
    """Return a structured guest profile, using LLM fallback when needed."""
    name = _extract_interviewee_name(title, description)
    profile: dict = {
        "name": name,
        "first_name": None,
        "last_name": None,
        "role": None,
        "organization": None,
        "location": None,
        "confidence": 0,
        "notes": None,
    }
    if name:
        parts = name.split(" ", 1)
        profile["first_name"] = parts[0]
        if len(parts) > 1:
            profile["last_name"] = parts[1]
        profile["confidence"] = 75
        return profile

    try:
        response = _get_anthropic_client().messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_INTERVIEWEE_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Podcast: {podcast_name}\n"
                        f"Episode title: {title}\n"
                        f"Show notes:\n{description[:4000]}"
                    ),
                }
            ],
        )
        response_text = response.content[0].text
        llm_profile = _parse_json_object(response_text)
    except Exception as exc:  # noqa: BLE001 — deliberate best-effort boundary:
        # LLM profile extraction is optional enrichment; on any failure
        # (API error, malformed JSON, ...) keep the heuristic profile.
        logger.debug("ListenNotes profile extraction fallback failed: %s", exc)
        return profile

    for key in ("name", "first_name", "last_name", "role", "organization", "location"):
        value = llm_profile.get(key)
        if value:
            profile[key] = value

    if profile["name"] and not profile["first_name"]:
        parts = profile["name"].split(" ", 1)
        profile["first_name"] = parts[0]
        if len(parts) > 1:
            profile["last_name"] = parts[1]
    llm_confidence = llm_profile.get("confidence")
    if isinstance(llm_confidence, (int, float)) and llm_confidence > 0:
        profile["confidence"] = llm_confidence
    if llm_profile.get("notes"):
        profile["notes"] = llm_profile["notes"]

    return profile


def _archetype_for_query(query: str) -> str:
    if query not in _QUERY_ARCHETYPE:
        raise KeyError(
            f"No archetype mapping for query {query!r} — add it to _QUERY_ARCHETYPE"
        )
    return _QUERY_ARCHETYPE[query]


def _build_lead(episode: dict, archetype: str) -> dict | None:
    """Normalize one ListenNotes episode into a raw lead."""
    raw_description = episode.get("description_original") or episode.get(
        "description", ""
    )
    raw_title = episode.get("title_original") or episode.get("title", "")
    url = episode.get("listennotes_url", "")
    if not raw_description or not url:
        return None

    title = _clean_text(raw_title)
    description = _clean_text(raw_description)
    podcast_name = _clean_text(
        episode.get("podcast", {}).get("title_original")
        or episode.get("podcast", {}).get("title", "")
    )
    interviewee_profile = _extract_interviewee_profile(title, description, podcast_name)
    emails = _extract_emails(raw_description, description)
    website_urls = _extract_website_urls(raw_description, description)

    lead = {
        "Archetype": archetype,
        "Source": "listennotes",
        "Source URL": url,
        "Status": "New",
        "Podcast Name": podcast_name,
        "Episode Title": title,
        "_content": f"{title}\n\n{description}",
        "_podcast": podcast_name,
        "_episode_id": episode.get("id", ""),
        "Interviewee Metadata": json.dumps(interviewee_profile, ensure_ascii=False),
    }
    if interviewee_profile.get("name"):
        lead["Name"] = interviewee_profile["name"]
    if interviewee_profile.get("first_name"):
        lead["First Name"] = interviewee_profile["first_name"]
    if interviewee_profile.get("last_name"):
        lead["Last Name"] = interviewee_profile["last_name"]
    if emails:
        lead["_emails"] = emails
        lead["_contact_clue"] = emails[0]
    elif website_urls:
        lead["_contact_clue"] = website_urls[0]
    if website_urls:
        lead["_website_urls"] = website_urls
        lead["Website URLs"] = "\n".join(website_urls)

    return lead


def _listennotes_search(query: str) -> list[dict]:
    """Search ListenNotes for podcast episodes. Returns raw leads."""
    for attempt in range(2):
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
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 429 and attempt == 0:
                retry_after = int(exc.response.headers.get("Retry-After", 60))
                logger.warning(
                    "ListenNotes rate limited for %r; retrying in %ds",
                    query,
                    retry_after,
                )
                time.sleep(retry_after)
                continue
            logger.warning("ListenNotes search failed (%s): %s", query, exc)
            return []

        archetype = _archetype_for_query(query)
        leads: list[dict] = []
        for episode in resp.json().get("results", []):
            lead = _build_lead(episode, archetype)
            if lead:
                leads.append(lead)
        return leads


def discover() -> list[dict]:
    """Search ListenNotes and return deduplicated raw leads."""
    seen_urls: set[str] = set()
    leads: list[dict] = []

    for query in LISTENNOTES_QUERIES:
        logger.info("ListenNotes: %.50s...", query)
        for lead in _listennotes_search(query):
            src = lead["Source URL"]
            if src not in seen_urls:
                seen_urls.add(src)
                leads.append(lead)
        time.sleep(LISTENNOTES_SLEEP_SECONDS)

    logger.info("Discovery complete: %d leads from ListenNotes", len(leads))
    return leads


if __name__ == "__main__":
    from modules.runner import run

    run(discover, id_field="Podcast Name", detail_field="Archetype")
