"""Unit tests for enrichment/hunter.py — all HTTP calls mocked."""

from unittest.mock import MagicMock, patch

import enrichment.hunter as h

# ---------------------------------------------------------------------------
# _extract_email_from_clue
# ---------------------------------------------------------------------------


def test_extract_email_finds_email():
    assert (
        h._extract_email_from_clue("Contact me at jane@example.com today")
        == "jane@example.com"
    )


def test_extract_email_returns_none_on_no_email():
    assert h._extract_email_from_clue("visit www.example.com") is None


def test_extract_email_returns_none_on_empty():
    assert h._extract_email_from_clue("") is None


# ---------------------------------------------------------------------------
# _domain_from_url
# ---------------------------------------------------------------------------


def test_domain_from_url_strips_www():
    assert h._domain_from_url("https://www.example.com/about") == "example.com"


def test_domain_from_url_no_scheme():
    assert h._domain_from_url("example.com/path") == "example.com"


def test_domain_from_url_returns_none_on_empty():
    assert h._domain_from_url("") is None


def test_domain_from_url_returns_none_on_email_string():
    # email-shaped strings should not be treated as URLs
    result = h._domain_from_url("jane@example.com")
    # urlparse treats this as a path, not a netloc — result should be None or not a bare domain
    assert result is None or "@" not in (result or "")


# ---------------------------------------------------------------------------
# _hunter_email_finder
# ---------------------------------------------------------------------------


def _mock_finder_response(email, score):
    mock = MagicMock()
    mock.json.return_value = {"data": {"email": email, "score": score}}
    return mock


@patch("enrichment.hunter.requests.get")
def test_hunter_email_finder_returns_email_above_threshold(mock_get):
    mock_get.return_value = _mock_finder_response("jane@example.com", 85)
    result = h._hunter_email_finder("example.com", "Jane", "Smith")
    assert result == ("jane@example.com", 85)


@patch("enrichment.hunter.requests.get")
def test_hunter_email_finder_returns_none_below_threshold(mock_get):
    mock_get.return_value = _mock_finder_response("jane@example.com", 50)
    result = h._hunter_email_finder("example.com", "Jane", "Smith")
    assert result is None


@patch("enrichment.hunter.requests.get")
def test_hunter_email_finder_http_error_returns_none(mock_get):
    import requests as req_lib

    mock_get.return_value.raise_for_status.side_effect = req_lib.HTTPError("404")
    result = h._hunter_email_finder("example.com", "Jane", "Smith")
    assert result is None


# ---------------------------------------------------------------------------
# _hunter_domain_search
# ---------------------------------------------------------------------------


def _mock_domain_search_response(emails):
    mock = MagicMock()
    mock.json.return_value = {"data": {"emails": emails}}
    return mock


@patch("enrichment.hunter.requests.get")
def test_hunter_domain_search_returns_highest_confidence(mock_get):
    mock_get.return_value = _mock_domain_search_response(
        [
            {"value": "low@example.com", "confidence": 72},
            {"value": "high@example.com", "confidence": 90},
        ]
    )
    result = h._hunter_domain_search("example.com")
    assert result == ("high@example.com", 90)


@patch("enrichment.hunter.requests.get")
def test_hunter_domain_search_filters_below_threshold(mock_get):
    mock_get.return_value = _mock_domain_search_response(
        [
            {"value": "weak@example.com", "confidence": 40},
        ]
    )
    result = h._hunter_domain_search("example.com")
    assert result is None


@patch("enrichment.hunter.requests.get")
def test_hunter_domain_search_http_error_returns_none(mock_get):
    import requests as req_lib

    mock_get.return_value.raise_for_status.side_effect = req_lib.HTTPError("429")
    result = h._hunter_domain_search("example.com")
    assert result is None


# ---------------------------------------------------------------------------
# enrich() — waterfall
# ---------------------------------------------------------------------------


def _base_lead(**kwargs):
    lead = {
        "Archetype": "health",
        "Source": "youtube",
        "Source URL": "https://www.youtube.com/watch?v=abc",
        "Status": "New",
        "First Name": "Jane",
        "Last Name": "Smith",
        "_contact_clue": None,
        "_disposition": "auto",
    }
    lead.update(kwargs)
    return lead


def test_enrich_uses_direct_email_from_clue():
    lead = _base_lead(_contact_clue="Reach me at jane@example.com")
    h.enrich(lead)
    assert lead["Email"] == "jane@example.com"
    assert lead["Email Confidence"] == 100
    assert lead["Contact Method"] == "email"


@patch("enrichment.hunter._hunter_domain_search")
@patch("enrichment.hunter._hunter_email_finder")
def test_enrich_calls_email_finder_with_name_and_domain(mock_finder, mock_search):
    mock_finder.return_value = ("jane@example.com", 80)
    lead = _base_lead(_contact_clue="https://example.com")
    h.enrich(lead)
    mock_finder.assert_called_once_with("example.com", "Jane", "Smith", None)
    assert lead["Email"] == "jane@example.com"


@patch("enrichment.hunter._hunter_domain_search")
@patch("enrichment.hunter._hunter_email_finder")
def test_enrich_falls_back_to_domain_search_when_no_name(mock_finder, mock_search):
    mock_search.return_value = ("info@example.com", 75)
    lead = _base_lead(
        _contact_clue="https://example.com", **{"First Name": "", "Last Name": ""}
    )
    h.enrich(lead)
    mock_finder.assert_not_called()
    mock_search.assert_called_once_with("example.com", None)
    assert lead["Email"] == "info@example.com"


@patch("enrichment.hunter._hunter_domain_search")
@patch("enrichment.hunter._hunter_email_finder")
def test_enrich_falls_back_to_domain_search_when_finder_fails(mock_finder, mock_search):
    mock_finder.return_value = None
    mock_search.return_value = ("info@example.com", 75)
    lead = _base_lead(_contact_clue="https://example.com")
    h.enrich(lead)
    assert lead["Email"] == "info@example.com"


@patch("enrichment.hunter._hunter_domain_search")
@patch("enrichment.hunter._hunter_email_finder")
def test_enrich_no_domain_sets_no_email(mock_finder, mock_search):
    lead = _base_lead(
        _contact_clue=None,
        **{"Source URL": "https://www.youtube.com/watch?v=abc"},
    )
    # youtube.com is a valid domain but the email finder would normally fail;
    # in this test both are mocked to return None
    mock_finder.return_value = None
    mock_search.return_value = None
    h.enrich(lead)
    assert "Email" not in lead


@patch("enrichment.hunter._hunter_domain_search")
@patch("enrichment.hunter._hunter_email_finder")
def test_enrich_returns_lead_unchanged_on_complete_failure(mock_finder, mock_search):
    mock_finder.return_value = None
    mock_search.return_value = None
    lead = _base_lead(_contact_clue=None, **{"Source URL": ""})
    result = h.enrich(lead)
    assert result is lead
    assert "Email" not in lead


# ---------------------------------------------------------------------------
# Reddit DM fallback
# ---------------------------------------------------------------------------


@patch("enrichment.hunter._hunter_domain_search")
@patch("enrichment.hunter._hunter_email_finder")
def test_enrich_skips_hunter_for_platform_source_domain(mock_finder, mock_search):
    """reddit.com Source URL must never be sent to Hunter."""
    lead = _base_lead(
        Source="reddit",
        **{"Source URL": "https://www.reddit.com/r/UberDrivers/comments/abc/"},
        _contact_clue=None,
    )
    h.enrich(lead)
    mock_finder.assert_not_called()
    mock_search.assert_not_called()


@patch("enrichment.hunter._hunter_domain_search")
@patch("enrichment.hunter._hunter_email_finder")
def test_enrich_skips_hunter_for_platform_clue_domain(mock_finder, mock_search):
    """A reddit.com URL in _contact_clue must also never be sent to Hunter."""
    lead = _base_lead(
        Source="reddit",
        **{"Source URL": "https://www.reddit.com/r/UberDrivers/comments/abc/"},
        **{"Reddit Username": "u/johndoe"},
        _contact_clue="https://www.reddit.com/r/other_post/",
    )
    h.enrich(lead)
    mock_finder.assert_not_called()
    mock_search.assert_not_called()
    assert lead["Contact Method"] == "reddit_dm"


@patch("enrichment.hunter._hunter_domain_search")
@patch("enrichment.hunter._hunter_email_finder")
def test_enrich_sets_reddit_dm_when_no_email_found(mock_finder, mock_search):
    mock_finder.return_value = None
    mock_search.return_value = None
    lead = _base_lead(
        Source="reddit",
        **{"Source URL": "https://www.reddit.com/r/UberDrivers/comments/abc/"},
        **{"Reddit Username": "u/johndoe"},
        _contact_clue=None,
    )
    h.enrich(lead)
    assert lead["Contact Method"] == "reddit_dm"
    assert lead["Contact Value"] == "https://www.reddit.com/user/johndoe"
    assert "Email" not in lead


@patch("enrichment.hunter._hunter_domain_search")
@patch("enrichment.hunter._hunter_email_finder")
def test_enrich_email_takes_priority_over_reddit_dm(mock_finder, mock_search):
    mock_finder.return_value = ("jane@example.com", 85)
    lead = _base_lead(
        Source="reddit",
        **{"Source URL": "https://www.reddit.com/r/UberDrivers/comments/abc/"},
        **{"Reddit Username": "u/johndoe"},
        _contact_clue="https://example.com",
    )
    h.enrich(lead)
    assert lead["Contact Method"] == "email"
    assert lead["Email"] == "jane@example.com"


@patch("enrichment.hunter._hunter_domain_search")
@patch("enrichment.hunter._hunter_email_finder")
def test_enrich_reddit_dm_skipped_for_deleted_author(mock_finder, mock_search):
    mock_finder.return_value = None
    mock_search.return_value = None
    lead = _base_lead(
        Source="reddit",
        **{"Source URL": "https://www.reddit.com/r/UberDrivers/comments/abc/"},
        **{"Reddit Username": "[deleted]"},
        _contact_clue=None,
    )
    h.enrich(lead)
    assert "Contact Method" not in lead
