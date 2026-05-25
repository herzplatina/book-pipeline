"""YouTube discovery module — Archetypes: health, driver, criminal.

discover() returns raw leads with ``_content`` set to title + description + transcript.
Scoring is handled by the shared ``scoring.claude_scorer`` module (Session 3).
"""

import logging
import time

from googleapiclient.discovery import build
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from config.settings import (
    YOUTUBE_API_KEY,
    YOUTUBE_FILTERS,
    YOUTUBE_SEARCH_QUERIES,
    YOUTUBE_SLEEP_SECONDS,
)

logger = logging.getLogger(__name__)

_YT_BASE_URL = "https://www.youtube.com/watch?v="


def _build_client():
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY, cache_discovery=False)


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
        segments = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
        return " ".join(seg["text"] for seg in segments)
    except (TranscriptsDisabled, NoTranscriptFound):
        return ""
    except Exception as exc:
        logger.warning("Transcript fetch failed for %s: %s", video_id, exc)
        return ""


def _build_lead(item: dict, transcript: str, archetype: str) -> dict:
    snippet = item.get("snippet", {})
    video_id = item["id"]["videoId"]
    title = snippet.get("title", "")
    description = snippet.get("description", "")
    channel = snippet.get("channelTitle", "")

    parts = [p for p in (title, description, transcript) if p]
    content = "\n\n".join(parts)

    return {
        "Archetype": archetype,
        "Source": "youtube",
        "Source URL": f"{_YT_BASE_URL}{video_id}",
        "Status": "New",
        "_content": content,
        "_video_id": video_id,
        "_channel": channel,
    }


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
            except Exception as exc:
                logger.error("YouTube search failed: %s", exc)
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
