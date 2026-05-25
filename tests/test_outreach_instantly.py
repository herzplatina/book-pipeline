"""Unit tests for outreach/instantly.py — all HTTP calls and Airtable mocked."""

from unittest.mock import MagicMock, patch

import outreach.instantly as inst


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lead(**kwargs):
    base = {
        "Archetype": "health",
        "Source": "youtube",
        "Source URL": "https://www.youtube.com/watch?v=abc",
        "Status": "New",
        "Email": "jane@example.com",
        "First Name": "Jane",
        "Last Name": "Smith",
        "Story Summary": "Jane overcame cancer and now coaches others.",
        "_disposition": "auto",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# route()
# ---------------------------------------------------------------------------


def test_route_discard_returns_skip():
    lead = _lead(_disposition="discard")
    assert inst.route(lead) == "skip"


def test_route_extremist_returns_skip():
    lead = _lead(Archetype="extremist", _disposition="auto")
    assert inst.route(lead) == "skip"


def test_route_criminal_nonprofit_returns_skip():
    lead = _lead(Archetype="criminal", Source="nonprofit", _disposition="auto")
    assert inst.route(lead) == "skip"


def test_route_reddit_source_returns_review_queue():
    lead = _lead(Source="reddit", _disposition="auto")
    assert inst.route(lead) == "review_queue"


def test_route_no_email_returns_review_queue():
    lead = _lead(_disposition="auto")
    del lead["Email"]
    assert inst.route(lead) == "review_queue"


def test_route_no_campaign_configured_returns_review_queue(monkeypatch):
    monkeypatch.setitem(inst.INSTANTLY_CAMPAIGNS, "health", "")
    lead = _lead(Archetype="health", _disposition="auto")
    assert inst.route(lead) == "review_queue"


def test_route_auto_with_campaign_returns_instantly(monkeypatch):
    monkeypatch.setitem(inst.INSTANTLY_CAMPAIGNS, "health", "campaign-abc")
    lead = _lead(Archetype="health", _disposition="auto")
    assert inst.route(lead) == "instantly"


def test_route_review_disposition_returns_review_queue(monkeypatch):
    monkeypatch.setitem(inst.INSTANTLY_CAMPAIGNS, "health", "campaign-abc")
    lead = _lead(_disposition="review")
    assert inst.route(lead) == "review_queue"


def test_route_criminal_non_nonprofit_goes_to_review_not_skip():
    lead = _lead(Archetype="criminal", Source="youtube", _disposition="review")
    assert inst.route(lead) == "review_queue"


# ---------------------------------------------------------------------------
# dispatch() — Instantly path
# ---------------------------------------------------------------------------


@patch("outreach.instantly.requests.post")
def test_dispatch_instantly_sets_lead_id_and_status(mock_post, monkeypatch):
    monkeypatch.setitem(inst.INSTANTLY_CAMPAIGNS, "health", "campaign-abc")
    mock_post.return_value.json.return_value = {"id": "instantly-lead-001"}
    mock_post.return_value.raise_for_status = MagicMock()

    lead = _lead(_disposition="auto")
    inst.dispatch(lead)

    assert lead["Instantly Lead ID"] == "instantly-lead-001"
    assert lead["Status"] == "Contacted"
    assert lead["_outreach_decision"] == "instantly"


@patch("outreach.instantly.requests.post")
def test_dispatch_instantly_api_error_falls_back_to_review(mock_post, monkeypatch):
    monkeypatch.setitem(inst.INSTANTLY_CAMPAIGNS, "health", "campaign-abc")
    import requests as req_lib

    mock_post.return_value.raise_for_status.side_effect = req_lib.HTTPError("500")

    lead = _lead(_disposition="auto")
    inst.dispatch(lead)

    assert lead["_outreach_decision"] == "review_queue"


# ---------------------------------------------------------------------------
# dispatch() — review_queue path
# ---------------------------------------------------------------------------


def test_dispatch_review_queue_calls_airtable(monkeypatch):
    monkeypatch.setitem(inst.INSTANTLY_CAMPAIGNS, "health", "campaign-abc")
    mock_at = MagicMock()

    lead = _lead(_disposition="review")
    inst.dispatch(lead, airtable_client=mock_at)

    mock_at.add_to_manual_queue.assert_called_once()
    queued = mock_at.add_to_manual_queue.call_args[0][0]
    assert queued["Source URL"] == lead["Source URL"]
    assert queued["Status"] == "Pending"


def test_dispatch_review_queue_without_airtable_does_not_raise():
    lead = _lead(_disposition="review")
    result = inst.dispatch(lead, airtable_client=None)
    assert result["_outreach_decision"] == "review_queue"


# ---------------------------------------------------------------------------
# dispatch() — skip path
# ---------------------------------------------------------------------------


def test_dispatch_skip_does_not_call_instantly():
    lead = _lead(Archetype="extremist", _disposition="auto")
    mock_at = MagicMock()
    with patch("outreach.instantly.requests.post") as mock_post:
        inst.dispatch(lead, airtable_client=mock_at)
        mock_post.assert_not_called()
    mock_at.add_to_manual_queue.assert_not_called()
    assert lead["_outreach_decision"] == "skip"
