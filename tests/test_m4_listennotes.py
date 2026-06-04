"""Unit tests for modules/m4_listennotes.py — all external I/O is mocked."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import modules.m4_listennotes as m4
from config.settings import LISTENNOTES_QUERIES


@pytest.fixture(autouse=True)
def mock_llm_client():
    """Keep all LLM calls deterministic in unit tests."""

    class FakeAnthropic:
        def __init__(self, *args, **kwargs):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            payload = {
                "name": None,
                "first_name": None,
                "last_name": None,
                "role": None,
                "organization": None,
                "location": None,
                "confidence": 0,
                "notes": None,
            }
            return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])

    m4._anthropic_client = None
    with patch("modules.m4_listennotes.anthropic.Anthropic", FakeAnthropic):
        yield
    m4._anthropic_client = None


def _mock_ln_response(episodes):
    mock = MagicMock()
    mock.json.return_value = {"results": episodes}
    mock.raise_for_status = MagicMock()
    return mock


def _make_episode(
    title="Healing Podcast",
    description="Great story.",
    url="https://listennotes.com/e/abc",
):
    return {
        "id": "episode_123",
        "title_original": title,
        "description_original": description,
        "listennotes_url": url,
        "podcast": {"title_original": "Healing Show"},
    }


def test_build_lead_sets_podcast_fields_and_content():
    lead = m4._build_lead(_make_episode(), "health")

    assert lead is not None
    assert lead["Source"] == "listennotes"
    assert lead["Archetype"] == "health"
    assert lead["Podcast Name"] == "Healing Show"
    assert lead["Episode Title"] == "Healing Podcast"
    assert "Healing Podcast" in lead["_content"]
    assert "Great story." in lead["_content"]
    assert lead["_episode_id"] == "episode_123"
    assert lead["Interviewee Metadata"]
    assert "Name" not in lead
    assert "First Name" not in lead
    assert "Last Name" not in lead


def test_build_lead_extracts_interviewee_name_from_explicit_guest_cue():
    episode = _make_episode(
        title="Episode 28 - Former Prisoner Serves Inmates with Love and Opportunity",
        description="In this conversation, host Sarah talks with Anil David about prison ministry.",
    )

    with patch("modules.m4_listennotes.anthropic.Anthropic") as mock_llm:
        lead = m4._build_lead(episode, "criminal")

    assert lead is not None
    assert lead["Name"] == "Anil David"
    assert lead["First Name"] == "Anil"
    assert lead["Last Name"] == "David"
    assert "Interviewee Metadata" in lead
    mock_llm.assert_not_called()


def test_build_lead_extracts_interviewee_name_from_title_suffix():
    episode = _make_episode(title="I Changed My Mindset In Jail: Kieron Bryan")

    with patch("modules.m4_listennotes.anthropic.Anthropic") as mock_llm:
        lead = m4._build_lead(episode, "criminal")

    assert lead is not None
    assert lead["Name"] == "Kieron Bryan"
    mock_llm.assert_not_called()


def test_build_lead_uses_llm_metadata_when_available():
    class MetadataAnthropic:
        def __init__(self, *args, **kwargs):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            payload = {
                "name": "Anil David",
                "first_name": "Anil",
                "last_name": "David",
                "role": "founder",
                "organization": "Agape Connecting People",
                "location": "Asia",
                "confidence": 92,
                "notes": "Former prisoner and ministry leader",
            }
            return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])

    with patch("modules.m4_listennotes.anthropic.Anthropic", MetadataAnthropic):
        lead = m4._build_lead(
            _make_episode(
                description="In this conversation, host Sarah talks about prison ministry."
            ),
            "criminal",
        )

    assert lead is not None
    assert lead["Name"] == "Anil David"
    assert lead["First Name"] == "Anil"
    assert lead["Last Name"] == "David"
    metadata = json.loads(lead["Interviewee Metadata"])
    assert metadata["role"] == "founder"
    assert metadata["organization"] == "Agape Connecting People"


def test_build_lead_extracts_emails_and_website_urls_from_show_notes():
    episode = _make_episode(
        description=(
            'Contact Jane at jane@example.com. Visit <a href="https://janesbakery.com">'
            "Jane's site</a> or https://listennotes.com/e/ignore."
        )
    )

    lead = m4._build_lead(episode, "bluecollar")

    assert lead is not None
    assert lead["_emails"] == ["jane@example.com"]
    assert lead["_contact_clue"] == "jane@example.com"
    assert lead["_website_urls"] == ["https://janesbakery.com"]
    assert lead["Website URLs"] == "https://janesbakery.com"


def test_build_lead_uses_website_url_as_contact_clue_when_no_email():
    episode = _make_episode(
        description='Guest links: <a href="https://marcus.co">Marcus website</a>'
    )

    lead = m4._build_lead(episode, "criminal")

    assert lead is not None
    assert "_emails" not in lead
    assert lead["_contact_clue"] == "https://marcus.co"
    assert lead["Website URLs"] == "https://marcus.co"


@pytest.mark.parametrize(
    "episode",
    [
        _make_episode(description=""),
        _make_episode(url=""),
    ],
)
def test_build_lead_skips_missing_required_episode_fields(episode):
    assert m4._build_lead(episode, "health") is None


@patch("modules.m4_listennotes.requests.get")
def test_listennotes_search_returns_leads(mock_get):
    mock_get.return_value = _mock_ln_response([_make_episode()])

    leads = m4._listennotes_search("Joe Dispenza healing story")

    assert len(leads) == 1
    assert leads[0]["Source"] == "listennotes"
    assert leads[0]["Archetype"] == "health"


@patch("modules.m4_listennotes.requests.get")
def test_listennotes_search_http_error_returns_empty(mock_get):
    import requests as req_lib

    mock_get.return_value.raise_for_status.side_effect = req_lib.HTTPError("429")

    leads = m4._listennotes_search("former prisoner entrepreneur")

    assert leads == []


@patch("modules.m4_listennotes.time.sleep")
@patch("modules.m4_listennotes._listennotes_search")
def test_discover_deduplicates_urls(mock_search, mock_sleep):
    dup_lead = {
        "Archetype": "health",
        "Source": "listennotes",
        "Source URL": "https://listennotes.com/e/dup",
        "Status": "New",
        "_content": "Story.",
    }
    mock_search.return_value = [dup_lead]

    leads = m4.discover()

    urls = [lead["Source URL"] for lead in leads]
    assert urls.count("https://listennotes.com/e/dup") == 1


@patch("modules.m4_listennotes.time.sleep")
@patch("modules.m4_listennotes._listennotes_search")
def test_discover_searches_all_listennotes_queries(mock_search, mock_sleep):
    mock_search.return_value = []

    m4.discover()

    assert mock_search.call_count == len(LISTENNOTES_QUERIES)
