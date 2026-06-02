"""YouTube discovery module — Archetypes: health, driver, criminal.

discover() returns raw leads with ``_content`` set to title + description + transcript.
Scoring is handled by the shared ``scoring.claude_scorer`` module (Session 3).
"""

import logging
import re
import time

from googleapiclient.discovery import build
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from config.settings import (
    YOUTUBE_FILTERS,
    YOUTUBE_SEARCH_QUERIES,
    YOUTUBE_SLEEP_SECONDS,
    require_env,
)

logger = logging.getLogger(__name__)

_YT_BASE_URL = "https://www.youtube.com/watch?v="
_YT_CHANNEL_BASE_URL = "https://www.youtube.com/channel/"
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_NAME_RE = re.compile(
    r"\b(?:my name is|i am|i'm|this is|meet|featuring|interview with|with)\s+"
    r"([A-Za-z][A-Za-z'-]+(?:\s+[A-Za-z][A-Za-z'-]+){1,3})\b",
    re.IGNORECASE,
)
_NAME_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "but",
    "for",
    "from",
    "going",
    "here",
    "in",
    "not",
    "of",
    "on",
    "or",
    "really",
    "so",
    "that",
    "the",
    "this",
    "to",
    "today",
    "very",
    "we",
    "when",
    "where",
    "who",
    "with",
    "you",
}


def _build_client():
    return build(
        "youtube",
        "v3",
        developerKey=require_env("YOUTUBE_API_KEY"),
        cache_discovery=False,
    )


def _youtube_search(client, query: str) -> list[dict]:
    """Call YouTube Data API search.list and return raw items."""
    request = client.search().list(
        q=query,
        part="snippet",
        type=YOUTUBE_FILTERS["type"],
        videoDuration=YOUTUBE_FILTERS["videoDuration"],
        maxResults=YOUTUBE_FILTERS["maxResults"],
        order=YOUTUBE_FILTERS["order"],
    )
    return request.execute().get("items", [])


def _get_transcript(video_id: str) -> str:
    """Fetch English transcript text. Returns empty string on any failure."""
    try:
        segments = _fetch_transcript_segments(video_id)
        return " ".join(
            segment["text"] if isinstance(segment, dict) else segment.text
            for segment in segments
        )
    except (TranscriptsDisabled, NoTranscriptFound):
        return ""
    except Exception:
        logger.exception("Transcript fetch failed for video_id=%s", video_id)
        return ""


def _fetch_transcript_segments(video_id: str):
    """Call either supported youtube-transcript-api interface."""
    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        return YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
    return YouTubeTranscriptApi().fetch(video_id, languages=["en"])


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _extract_emails(*texts: str) -> list[str]:
    """Extract email addresses from video-owned text only."""
    combined = "\n".join(text for text in texts if text)
    return _dedupe([email.rstrip(".,;:") for email in _EMAIL_RE.findall(combined)])


def _normalize_name_candidate(candidate: str) -> str | None:
    words = [word.strip(" .,:;") for word in candidate.split()]
    cleaned: list[str] = []
    for word in words:
        if word.lower() in _NAME_STOP_WORDS:
            break
        cleaned.append(word)

    if len(cleaned) < 2:
        return None
    return " ".join(
        word if any(char.isupper() for char in word) else word.title()
        for word in cleaned
    )


def _extract_name_candidates(*texts: str) -> list[str]:
    """Conservatively extract full-name candidates from description/transcript text."""
    combined = "\n".join(text for text in texts if text)
    candidates = [
        candidate
        for match in _NAME_RE.finditer(combined)
        if (candidate := _normalize_name_candidate(match.group(1))) is not None
    ]
    return _dedupe(candidates)


def _build_lead(item: dict, transcript: str, archetype: str) -> dict:
    snippet = item.get("snippet", {})
    video_id = item["id"]["videoId"]
    title = snippet.get("title", "")
    description = snippet.get("description", "")
    channel_id = snippet.get("channelId", "")
    channel = snippet.get("channelTitle", "")

    parts = [p for p in (title, description, transcript) if p]
    content = "\n\n".join(parts)
    emails = _extract_emails(description, transcript)
    name_candidates = _extract_name_candidates(description, transcript)

    lead = {
        "Archetype": archetype,
        "Source": "youtube",
        "Source URL": f"{_YT_BASE_URL}{video_id}",
        "Status": "New",
        "_content": content,
        "_video_id": video_id,
        "_channel": channel,
    }
    if channel_id:
        lead["Channel URL"] = f"{_YT_CHANNEL_BASE_URL}{channel_id}"
    if emails:
        lead["_emails"] = emails
        lead["_contact_clue"] = emails[0]
    if name_candidates:
        lead["_name_candidates"] = name_candidates

    return lead


def discover() -> list[dict]:
    """Search YouTube for each archetype's query set and return raw leads.

    Returns:
        All unique video leads with ``_content`` set. Scoring and threshold filtering
        are handled downstream by ``scoring.claude_scorer`` and the orchestrator.
    """
    client = _build_client()
    seen_ids: set[str] = set()
    leads: list[dict] = []

    total_queries = sum(len(qs) for qs in YOUTUBE_SEARCH_QUERIES.values())
    done = 0

    for archetype, queries in YOUTUBE_SEARCH_QUERIES.items():
        for query in queries:
            done += 1
            logger.info(
                "[%d/%d] YouTube: %s / %.50s...",
                done,
                total_queries,
                archetype,
                query,
            )

            try:
                items = _youtube_search(client, query)
            except Exception:
                logger.exception("YouTube search failed for archetype=%s", archetype)
                time.sleep(YOUTUBE_SLEEP_SECONDS)
                continue

            for item in items:
                try:
                    video_id = item["id"]["videoId"]
                except KeyError:
                    continue

                if video_id in seen_ids:
                    continue
                seen_ids.add(video_id)

                transcript = _get_transcript(video_id)
                lead = _build_lead(item, transcript, archetype)
                leads.append(lead)
                logger.debug("Queued %s (%s)", video_id, archetype)

            time.sleep(YOUTUBE_SLEEP_SECONDS)

    logger.info(
        "Discovery complete: %d leads queued from %d unique videos scanned",
        len(leads),
        len(seen_ids),
    )
    return leads


if __name__ == "__main__":
    from modules.runner import run

    run(discover)
