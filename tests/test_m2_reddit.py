"""Unit tests for modules/m2_reddit.py — all external I/O is mocked."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import modules.m2_reddit as m2
from config.settings import REDDIT_FILTERS, SUBREDDITS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_praw_post(
    post_id="abc123",
    title="I started a business after losing my job",
    selftext="Long story about turning life around.",
    score=250,
    author="u/someone",
    permalink="/r/UberDrivers/comments/abc123/i_started_a_business/",
):
    post = SimpleNamespace(
        id=post_id,
        title=title,
        selftext=selftext,
        score=score,
        author=SimpleNamespace(__str__=lambda s: author),
        permalink=permalink,
    )
    # Make str(post.author) work
    post.author = type("Author", (), {"__str__": lambda s: author})()
    return post


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
# _keyword_match
# ---------------------------------------------------------------------------


def test_keyword_match_returns_true_on_match():
    assert m2._keyword_match("I started a business last year")


def test_keyword_match_case_insensitive():
    assert m2._keyword_match("I Started A Business after everything")


def test_keyword_match_returns_false_on_no_match():
    assert not m2._keyword_match("Just a random post about cooking")


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
    assert lead["_post_id"] == "abc"
    assert lead["_reddit_author"] == "u/jane"
    assert lead["_subreddit"] == "Recovery"


def test_build_lead_content_joins_title_and_selftext():
    lead = m2._build_lead("id", "Title", "Body text.", "author", "/r/x/", "health", "x")
    assert "Title" in lead["_content"]
    assert "Body text." in lead["_content"]


def test_build_lead_has_no_scoring_fields():
    lead = m2._build_lead("id", "Title", "Body.", "author", "/r/x/", "health", "x")
    assert "Claude Score" not in lead
    assert "Name" not in lead


# ---------------------------------------------------------------------------
# _praw_fetch
# ---------------------------------------------------------------------------


def test_praw_fetch_filters_low_score():
    mock_reddit = MagicMock()
    low_score_post = _make_praw_post(score=REDDIT_FILTERS["min_score"] - 1)
    mock_reddit.subreddit.return_value.top.return_value = [low_score_post]

    leads = m2._praw_fetch(mock_reddit, "UberDrivers", "driver")
    assert leads == []


def test_praw_fetch_filters_no_keyword_match():
    mock_reddit = MagicMock()
    post = _make_praw_post(
        score=500,
        title="What's the best pizza in town?",
        selftext="Looking for recommendations.",
    )
    mock_reddit.subreddit.return_value.top.return_value = [post]

    leads = m2._praw_fetch(mock_reddit, "UberDrivers", "driver")
    assert leads == []


def test_praw_fetch_returns_matching_lead():
    mock_reddit = MagicMock()
    post = _make_praw_post(score=300, title="I started a business after Uber")
    mock_reddit.subreddit.return_value.top.return_value = [post]

    leads = m2._praw_fetch(mock_reddit, "UberDrivers", "driver")
    assert len(leads) == 1
    assert leads[0]["Archetype"] == "driver"
    assert leads[0]["Source"] == "reddit"


def test_praw_fetch_handles_exception_gracefully():
    mock_reddit = MagicMock()
    mock_reddit.subreddit.side_effect = Exception("API error")

    leads = m2._praw_fetch(mock_reddit, "UberDrivers", "driver")
    assert leads == []


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
@patch("modules.m2_reddit._praw_fetch")
@patch("modules.m2_reddit._praw_client")
def test_discover_returns_leads(mock_client, mock_praw, mock_arctic, mock_sleep):
    mock_praw.return_value = [
        m2._build_lead("p1", "Title", "Body", "u/x", "/r/x/", "driver", "UberDrivers")
    ]
    mock_arctic.return_value = []

    leads = m2.discover()
    assert len(leads) >= 1
    assert leads[0]["Source"] == "reddit"
    assert "Claude Score" not in leads[0]


@patch("modules.m2_reddit.time.sleep")
@patch("modules.m2_reddit._arctic_fetch")
@patch("modules.m2_reddit._praw_fetch")
@patch("modules.m2_reddit._praw_client")
def test_discover_deduplicates_across_passes(
    mock_client, mock_praw, mock_arctic, mock_sleep
):
    shared_lead = m2._build_lead(
        "dup_id",
        "Title",
        "Body",
        "u/x",
        "/r/x/comments/dup_id/",
        "driver",
        "UberDrivers",
    )
    mock_praw.return_value = [shared_lead]
    mock_arctic.return_value = [shared_lead]

    leads = m2.discover()
    ids = [lead["_post_id"] for lead in leads]
    assert ids.count("dup_id") == 1


@patch("modules.m2_reddit.time.sleep")
@patch("modules.m2_reddit._arctic_fetch")
@patch("modules.m2_reddit._praw_fetch")
@patch("modules.m2_reddit._praw_client")
def test_discover_covers_all_archetypes(
    mock_client, mock_praw, mock_arctic, mock_sleep
):
    call_counter = {"n": 0}

    def unique_lead(reddit, subreddit, archetype):
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

    mock_praw.side_effect = unique_lead
    mock_arctic.return_value = []

    leads = m2.discover()
    archetypes_found = {lead["Archetype"] for lead in leads}
    assert archetypes_found == set(SUBREDDITS.keys())


@patch("modules.m2_reddit.time.sleep")
@patch("modules.m2_reddit._arctic_fetch")
@patch("modules.m2_reddit._praw_fetch")
@patch("modules.m2_reddit._praw_client")
def test_discover_sleeps_between_calls(mock_client, mock_praw, mock_arctic, mock_sleep):
    mock_praw.return_value = []
    mock_arctic.return_value = []

    m2.discover()

    total_subreddits = sum(len(v) for v in SUBREDDITS.values())
    arctic_calls = total_subreddits * m2._ARCTIC_MAX_KEYWORDS
    expected_sleeps = total_subreddits + arctic_calls
    assert mock_sleep.call_count == expected_sleeps
