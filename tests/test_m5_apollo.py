"""Unit tests for modules/m5_apollo.py — all HTTP calls mocked."""

from unittest.mock import patch

import modules.m5_apollo as m5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_person(
    pid="apollo_001",
    first="Jane",
    last="Smith",
    email="jane@example.com",
    headline="Founder after Covid layoff",
    title="CEO",
    org="Jane's Bakery",
    linkedin="https://linkedin.com/in/janesmith",
):
    return {
        "id": pid,
        "first_name": first,
        "last_name": last,
        "email": email,
        "email_confidence_cd": 82,
        "headline": headline,
        "title": title,
        "organization": {"name": org},
        "linkedin_url": linkedin,
        "employment_history": [
            {
                "title": "Line Cook",
                "organization_name": "Diner Co",
                "start_date": "2018-01",
                "end_date": "2020-04",
            }
        ],
    }


# ---------------------------------------------------------------------------
# _build_lead
# ---------------------------------------------------------------------------


def test_build_lead_sets_required_fields():
    lead = m5._build_lead(_make_person())
    assert lead["Archetype"] == "bluecollar"
    assert lead["Source"] == "apollo"
    assert lead["Status"] == "New"
    assert lead["Name"] == "Jane Smith"
    assert lead["First Name"] == "Jane"
    assert lead["Last Name"] == "Smith"
    assert lead["_apollo_id"] == "apollo_001"


def test_build_lead_sets_email_fields():
    lead = m5._build_lead(_make_person())
    assert lead["Email"] == "jane@example.com"
    assert lead["Email Confidence"] == 82
    assert lead["Contact Method"] == "email"


def test_build_lead_content_includes_headline_and_history():
    lead = m5._build_lead(_make_person())
    assert "Founder after Covid layoff" in lead["_content"]
    assert "Line Cook" in lead["_content"]


def test_build_lead_returns_none_when_no_name():
    person = _make_person(first="", last="")
    assert m5._build_lead(person) is None


def test_build_lead_has_no_scoring_fields():
    lead = m5._build_lead(_make_person())
    assert "Claude Score" not in lead
    assert "Story Summary" not in lead


def test_build_lead_no_email_omits_email_fields():
    person = _make_person(email="")
    lead = m5._build_lead(person)
    assert "Email" not in lead
    assert "Contact Method" not in lead


def test_build_lead_falls_back_to_apollo_url_when_no_linkedin():
    person = _make_person(linkedin="")
    lead = m5._build_lead(person)
    assert "apollo.io" in lead["Source URL"]


# ---------------------------------------------------------------------------
# _apollo_search
# ---------------------------------------------------------------------------


@patch("modules.m5_apollo.requests.post")
def test_apollo_search_returns_people(mock_post):
    mock_post.return_value.json.return_value = {"people": [_make_person()]}
    mock_post.return_value.raise_for_status = lambda: None

    people = m5._apollo_search(1)
    assert len(people) == 1


@patch("modules.m5_apollo.requests.post")
def test_apollo_search_http_error_returns_empty(mock_post):
    import requests as req_lib

    mock_post.return_value.raise_for_status.side_effect = req_lib.HTTPError("403")
    people = m5._apollo_search(1)
    assert people == []


# ---------------------------------------------------------------------------
# discover()
# ---------------------------------------------------------------------------


@patch("modules.m5_apollo.time.sleep")
@patch("modules.m5_apollo._apollo_search")
def test_discover_returns_leads(mock_search, mock_sleep):
    mock_search.return_value = [_make_person()]
    leads = m5.discover(max_pages=1)
    assert len(leads) == 1
    assert leads[0]["Archetype"] == "bluecollar"
    assert "_content" in leads[0]


@patch("modules.m5_apollo.time.sleep")
@patch("modules.m5_apollo._apollo_search")
def test_discover_deduplicates_by_apollo_id(mock_search, mock_sleep):
    mock_search.return_value = [
        _make_person(pid="same_id"),
        _make_person(pid="same_id"),
    ]
    leads = m5.discover(max_pages=1)
    ids = [lead["_apollo_id"] for lead in leads]
    assert ids.count("same_id") == 1


@patch("modules.m5_apollo.time.sleep")
@patch("modules.m5_apollo._apollo_search")
def test_discover_stops_on_empty_page(mock_search, mock_sleep):
    mock_search.side_effect = [[_make_person()], []]
    m5.discover(max_pages=3)
    assert mock_search.call_count == 2


@patch("modules.m5_apollo.time.sleep")
@patch("modules.m5_apollo._apollo_search")
def test_discover_respects_max_pages(mock_search, mock_sleep):
    mock_search.return_value = [_make_person(pid=f"id_{i}") for i in range(5)]
    m5.discover(max_pages=2)
    assert mock_search.call_count == 2


@patch("modules.m5_apollo.time.sleep")
@patch("modules.m5_apollo._apollo_search")
def test_discover_skips_leads_with_no_name(mock_search, mock_sleep):
    mock_search.return_value = [_make_person(first="", last="")]
    leads = m5.discover(max_pages=1)
    assert leads == []
