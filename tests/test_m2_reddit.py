"""Unit tests for modules/m2_reddit.py — all external I/O is mocked."""

from unittest.mock import MagicMock, patch

import modules.m2_reddit as m2
from config.settings import REDDIT_FILTERS, SUBREDDITS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_arctic_item(
    post_id="xyz789",
    title="Turned my life around after prison",
    selftext="Details about second chance.",
    score=180,
    author="u/user2",
    permalink="/r/reentry/comments/xyz789/turned_my_life/",
):
    return {
        "id": post_id,
        "title": title,
        "selftext": selftext,
        "score": score,
        "author": author,
        "permalink": permalink,
    }


# ---------------------------------------------------------------------------
# _build_lead
# ---------------------------------------------------------------------------


def test_build_lead_sets_required_fields():
    lead = m2._build_lead(
        post_id="abc",
        title="My Story",
        selftext="Details here.",
        author="u/jane",
        permalink="/r/Recovery/comments/abc/my_story/",
        archetype="health",
        subreddit="Recovery",
    )
    assert lead["Archetype"] == "health"
    assert lead["Source"] == "reddit"
    assert (
        lead["Source URL"] == "https://www.reddit.com/r/Recovery/comments/abc/my_story/"
    )
    assert lead["Status"] == "New"
    assert lead["Reddit Username"] == "u/jane"
    assert lead["Subreddit"] == "Recovery"
    assert lead["_post_id"] == "abc"


def test_build_lead_content_joins_title_and_selftext():
    lead = m2._build_lead("id", "Title", "Body text.", "author", "/r/x/", "health", "x")
    assert "Title" in lead["_content"]
    assert "Body text." in lead["_content"]


def test_build_lead_has_no_scoring_fields():
    lead = m2._build_lead("id", "Title", "Body.", "author", "/r/x/", "health", "x")
    assert "Claude Score" not in lead
    assert "Name" not in lead


# ---------------------------------------------------------------------------
# _arctic_fetch
# ---------------------------------------------------------------------------


@patch("modules.m2_reddit.requests.get")
def test_arctic_fetch_returns_leads(mock_get):
    mock_get.return_value.json.return_value = {"data": [_make_arctic_item(score=200)]}
    mock_get.return_value.raise_for_status = MagicMock()

    leads = m2._arctic_fetch("reentry", "second chance", "criminal")
    assert len(leads) == 1
    assert leads[0]["Archetype"] == "criminal"
    assert leads[0]["Source"] == "reddit"
    assert leads[0]["Reddit Username"] == "u/user2"
    assert leads[0]["Subreddit"] == "reentry"


@patch("modules.m2_reddit.requests.get")
def test_arctic_fetch_filters_low_score(mock_get):
    low = _make_arctic_item(score=REDDIT_FILTERS["min_score"] - 1)
    mock_get.return_value.json.return_value = {"data": [low]}
    mock_get.return_value.raise_for_status = MagicMock()

    leads = m2._arctic_fetch("reentry", "second chance", "criminal")
    assert leads == []


@patch("modules.m2_reddit.requests.get")
def test_arctic_fetch_http_error_returns_empty(mock_get):
    import requests as req_lib

    mock_get.return_value.raise_for_status.side_effect = req_lib.HTTPError("429")

    leads = m2._arctic_fetch("reentry", "second chance", "criminal")
    assert leads == []


# ---------------------------------------------------------------------------
# discover() — all external I/O mocked
# ---------------------------------------------------------------------------


@patch("modules.m2_reddit.time.sleep")
@patch("modules.m2_reddit._arctic_fetch")
def test_discover_returns_leads(mock_arctic, mock_sleep):
    mock_arctic.return_value = [
        m2._build_lead("p1", "Title", "Body", "u/x", "/r/x/", "driver", "UberDrivers")
    ]

    leads = m2.discover()
    assert len(leads) >= 1
    assert leads[0]["Source"] == "reddit"
    assert "Claude Score" not in leads[0]


@patch("modules.m2_reddit.time.sleep")
@patch("modules.m2_reddit._arctic_fetch")
def test_discover_deduplicates_same_post_across_keywords(mock_arctic, mock_sleep):
    shared_lead = m2._build_lead(
        "dup_id",
        "Title",
        "Body",
        "u/x",
        "/r/x/comments/dup_id/",
        "driver",
        "UberDrivers",
    )
    mock_arctic.return_value = [shared_lead]

    leads = m2.discover()
    ids = [lead["_post_id"] for lead in leads]
    assert ids.count("dup_id") == 1


@patch("modules.m2_reddit.time.sleep")
@patch("modules.m2_reddit._arctic_fetch")
def test_discover_covers_all_archetypes(mock_arctic, mock_sleep):
    call_counter = {"n": 0}

    def unique_lead(subreddit, keyword, archetype):
        call_counter["n"] += 1
        return [
            m2._build_lead(
                f"p{call_counter['n']}",
                "Title",
                "Body",
                "u/x",
                "/r/x/",
                archetype,
                subreddit,
            )
        ]

    mock_arctic.side_effect = unique_lead

    leads = m2.discover()
    archetypes_found = {lead["Archetype"] for lead in leads}
    assert archetypes_found == set(SUBREDDITS.keys())


@patch("modules.m2_reddit.time.sleep")
@patch("modules.m2_reddit._arctic_fetch")
def test_discover_sleeps_between_calls(mock_arctic, mock_sleep):
    mock_arctic.return_value = []

    m2.discover()

    total_subreddits = sum(len(v) for v in SUBREDDITS.values())
    expected_sleeps = total_subreddits * m2._ARCTIC_MAX_KEYWORDS
    assert mock_sleep.call_count == expected_sleeps


# ---------------------------------------------------------------------------
# run_smoke_test()
# ---------------------------------------------------------------------------


@patch("modules.m2_reddit._arctic_fetch")
def test_run_smoke_test_returns_summary_dict(mock_arctic):
    mock_arctic.return_value = [
        m2._build_lead(
            "a1", "Title", "Body", "u/x", "/r/UberDrivers/a1/", "driver", "UberDrivers"
        ),
        m2._build_lead(
            "a2",
            "Title2",
            "Body2",
            "u/y",
            "/r/UberDrivers/a2/",
            "driver",
            "UberDrivers",
        ),
    ]

    result = m2.run_smoke_test()

    assert result["arctic_leads"] == 2
    assert result["subreddit"] == "UberDrivers"
    assert "keyword" in result


@patch("modules.m2_reddit._arctic_fetch")
def test_run_smoke_test_handles_empty_results(mock_arctic):
    mock_arctic.return_value = []

    result = m2.run_smoke_test()

    assert result["arctic_leads"] == 0


@patch("modules.m2_reddit._arctic_fetch")
def test_run_smoke_test_raises_on_malformed_lead(mock_arctic):
    import pytest

    mock_arctic.return_value = [{"Archetype": "driver"}]  # missing required keys

    with pytest.raises(RuntimeError, match="missing required keys"):
        m2.run_smoke_test()
