"""Unit tests for modules/m1_youtube.py — all external I/O is mocked."""

from types import SimpleNamespace
from unittest.mock import patch

import modules.m1_youtube as m1
from config.settings import YOUTUBE_SEARCH_QUERIES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    video_id="abc123",
    title="Healing Story",
    channel="MyChannel",
    channel_id="channel_123",
):
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": title,
            "description": "A description of the video.",
            "channelTitle": channel,
            "channelId": channel_id,
        },
    }


# ---------------------------------------------------------------------------
# _get_transcript
# ---------------------------------------------------------------------------


def test_get_transcript_supports_new_fetch_api():
    class FakeTranscriptApi:
        def fetch(self, video_id, languages):
            return [
                SimpleNamespace(text="hello"),
                SimpleNamespace(text="world"),
            ]

    with patch.object(m1, "YouTubeTranscriptApi", FakeTranscriptApi):
        assert m1._get_transcript("abc123") == "hello world"


# ---------------------------------------------------------------------------
# _build_lead
# ---------------------------------------------------------------------------


def test_build_lead_sets_required_fields():
    item = _make_item()
    lead = m1._build_lead(item, "transcript text", "health")

    assert lead["Archetype"] == "health"
    assert lead["Source"] == "youtube"
    assert lead["Source URL"] == "https://www.youtube.com/watch?v=abc123"
    assert lead["Status"] == "New"
    assert lead["_video_id"] == "abc123"
    assert lead["_channel"] == "MyChannel"
    assert lead["Channel URL"] == "https://www.youtube.com/channel/channel_123"


def test_build_lead_content_includes_title_description_transcript():
    item = _make_item(title="My Healing Story")
    lead = m1._build_lead(item, "the transcript text", "health")

    assert "My Healing Story" in lead["_content"]
    assert "A description of the video." in lead["_content"]
    assert "the transcript text" in lead["_content"]


def test_build_lead_extracts_contact_hints_from_description_and_transcript_only():
    item = _make_item(title="Title with Jane Ignored")
    item["snippet"]["description"] = (
        "Meet Jane Smith. Contact her at jane@example.com."
    )
    transcript = "Today I am Maria Garcia and you can reach me at maria@example.org."

    lead = m1._build_lead(item, transcript, "health")

    assert lead["_emails"] == ["jane@example.com", "maria@example.org"]
    assert lead["_contact_clue"] == "jane@example.com"
    assert lead["_name_candidates"] == ["Jane Smith", "Maria Garcia"]


def test_build_lead_does_not_extract_names_or_emails_from_channel_metadata():
    item = _make_item()
    item["snippet"]["channelTitle"] = "Jane Smith jane@example.com"

    lead = m1._build_lead(item, "", "health")

    assert "_emails" not in lead
    assert "_contact_clue" not in lead
    assert "_name_candidates" not in lead
    assert "_channel_id" not in lead
    assert "_channel_url" not in lead
    assert "_channel_description" not in lead
    assert lead["Channel URL"] == "https://www.youtube.com/channel/channel_123"


def test_build_lead_does_not_extract_urls_as_contact_clues():
    item = _make_item()
    item["snippet"]["description"] = "Portfolio: https://example.com/jane"

    lead = m1._build_lead(item, "", "health")

    assert "_contact_clue" not in lead


def test_build_lead_content_omits_empty_transcript():
    item = _make_item(title="Healing Story")
    lead = m1._build_lead(item, "", "health")

    assert "Healing Story" in lead["_content"]
    # Empty transcript must not add trailing separator
    assert not lead["_content"].endswith("\n\n")


def test_build_lead_has_no_scoring_fields():
    item = _make_item()
    lead = m1._build_lead(item, "", "driver")

    assert "Claude Score" not in lead
    assert "Name" not in lead
    assert "Story Summary" not in lead


# ---------------------------------------------------------------------------
# discover() — all external I/O mocked
# ---------------------------------------------------------------------------


@patch("modules.m1_youtube.time.sleep")
@patch("modules.m1_youtube._get_transcript")
@patch("modules.m1_youtube._youtube_search")
@patch("modules.m1_youtube._build_client")
def test_discover_returns_leads(mock_client, mock_search, mock_transcript, mock_sleep):
    mock_search.return_value = [_make_item()]
    mock_transcript.return_value = "Full transcript text."

    leads = m1.discover()

    assert len(leads) >= 1
    assert leads[0]["Source"] == "youtube"
    assert "_content" in leads[0]
    assert "Claude Score" not in leads[0]


@patch("modules.m1_youtube.time.sleep")
@patch("modules.m1_youtube._get_transcript")
@patch("modules.m1_youtube._youtube_search")
@patch("modules.m1_youtube._build_client")
def test_discover_deduplicates_video_ids(
    mock_client, mock_search, mock_transcript, mock_sleep
):
    # Same video_id returned by every archetype query
    mock_search.return_value = [_make_item(video_id="dup_id")]
    mock_transcript.return_value = "transcript"

    leads = m1.discover()

    ids = [lead["_video_id"] for lead in leads]
    assert ids.count("dup_id") == 1


@patch("modules.m1_youtube.time.sleep")
@patch("modules.m1_youtube._get_transcript")
@patch("modules.m1_youtube._youtube_search")
@patch("modules.m1_youtube._build_client")
def test_discover_search_error_continues(
    mock_client, mock_search, mock_transcript, mock_sleep
):
    mock_search.side_effect = Exception("API quota exceeded")

    leads = m1.discover()
    assert leads == []


@patch("modules.m1_youtube.time.sleep")
@patch("modules.m1_youtube._get_transcript")
@patch("modules.m1_youtube._youtube_search")
@patch("modules.m1_youtube._build_client")
def test_discover_skips_items_without_video_id(
    mock_client, mock_search, mock_transcript, mock_sleep
):
    # Simulate a channel/playlist result that has no id.videoId
    mock_search.return_value = [{"id": {"kind": "youtube#channel"}, "snippet": {}}]
    mock_transcript.return_value = ""

    leads = m1.discover()
    assert leads == []


@patch("modules.m1_youtube.time.sleep")
@patch("modules.m1_youtube._get_transcript")
@patch("modules.m1_youtube._youtube_search")
@patch("modules.m1_youtube._build_client")
def test_discover_covers_all_archetypes(
    mock_client, mock_search, mock_transcript, mock_sleep
):
    # Give each query a unique video_id so nothing is deduplicated
    call_counter = {"n": 0}

    def unique_item(*_args, **_kwargs):
        call_counter["n"] += 1
        return [_make_item(video_id=f"vid_{call_counter['n']}")]

    mock_search.side_effect = unique_item
    mock_transcript.return_value = ""

    leads = m1.discover()

    archetypes_found = {lead["Archetype"] for lead in leads}
    assert archetypes_found == set(YOUTUBE_SEARCH_QUERIES.keys())


@patch("modules.m1_youtube.time.sleep")
@patch("modules.m1_youtube._get_transcript")
@patch("modules.m1_youtube._youtube_search")
@patch("modules.m1_youtube._build_client")
def test_discover_sleeps_between_searches(
    mock_client, mock_search, mock_transcript, mock_sleep
):
    mock_search.return_value = []

    m1.discover()

    total_queries = sum(len(qs) for qs in YOUTUBE_SEARCH_QUERIES.values())
    assert mock_sleep.call_count == total_queries
