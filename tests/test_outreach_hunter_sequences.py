"""Unit tests for outreach/hunter_sequences.py — HTTP and Airtable mocked."""

from unittest.mock import MagicMock, patch

import outreach.hunter_sequences as hs


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


def test_route_discard_returns_skip():
    lead = _lead(_disposition="discard")
    assert hs.route(lead) == "skip"


def test_route_extremist_returns_review_queue():
    lead = _lead(Archetype="extremist", _disposition="auto")
    assert hs.route(lead) == "review_queue"


def test_route_criminal_nonprofit_returns_review_queue():
    lead = _lead(Archetype="criminal", Source="nonprofit", _disposition="auto")
    assert hs.route(lead) == "review_queue"


def test_route_reddit_source_returns_review_queue():
    lead = _lead(Source="reddit", _disposition="auto")
    assert hs.route(lead) == "review_queue"


def test_route_no_email_returns_review_queue():
    lead = _lead(_disposition="auto")
    del lead["Email"]
    assert hs.route(lead) == "review_queue"


def test_route_no_sequence_configured_returns_review_queue(monkeypatch):
    monkeypatch.setattr(hs, "HUNTER_SEQUENCE_ID", "")
    lead = _lead(Archetype="health", _disposition="auto")
    assert hs.route(lead) == "review_queue"


def test_route_auto_with_sequence_returns_hunter_sequence(monkeypatch):
    monkeypatch.setattr(hs, "HUNTER_SEQUENCE_ID", "sequence-abc")
    lead = _lead(Archetype="health", _disposition="auto")
    assert hs.route(lead) == "hunter_sequence"


def test_route_review_disposition_returns_review_queue(monkeypatch):
    monkeypatch.setattr(hs, "HUNTER_SEQUENCE_ID", "sequence-abc")
    lead = _lead(_disposition="review")
    assert hs.route(lead) == "review_queue"


@patch("outreach.hunter_sequences.requests.post")
def test_dispatch_hunter_sequence_sets_lead_id_and_status(mock_post, monkeypatch):
    monkeypatch.setattr(hs, "HUNTER_SEQUENCE_ID", "sequence-abc")
    mock_post.return_value.json.return_value = {
        "recipients_added": [{"id": "hunter-lead-001"}]
    }
    mock_post.return_value.raise_for_status = MagicMock()

    lead = _lead(_disposition="auto")
    hs.dispatch(lead)

    assert lead["Hunter Lead ID"] == "hunter-lead-001"
    assert lead["Hunter Sequence ID"] == "sequence-abc"
    assert lead["Status"] == "Contacted"
    assert lead["_outreach_decision"] == "hunter_sequence"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["emails"] == ["jane@example.com"]
    assert payload["custom_variables"]["archetype"] == "health"


@patch("outreach.hunter_sequences.requests.post")
def test_dispatch_hunter_sequence_handles_nested_data_response(mock_post, monkeypatch):
    monkeypatch.setattr(hs, "HUNTER_SEQUENCE_ID", "sequence-abc")
    mock_post.return_value.json.return_value = {
        "data": {"recipients_added": [{"lead_id": "hunter-lead-002"}]}
    }
    mock_post.return_value.raise_for_status = MagicMock()

    lead = _lead(_disposition="auto")
    hs.dispatch(lead)

    assert lead["Hunter Lead ID"] == "hunter-lead-002"
    assert lead["Status"] == "Contacted"
    assert lead["_outreach_decision"] == "hunter_sequence"


@patch("outreach.hunter_sequences.requests.post")
def test_dispatch_hunter_skipped_recipient_falls_back_to_review(mock_post, monkeypatch):
    monkeypatch.setattr(hs, "HUNTER_SEQUENCE_ID", "sequence-abc")
    mock_post.return_value.json.return_value = {
        "recipients_added": [],
        "skipped_recipients": [{"email": "jane@example.com"}],
    }
    mock_post.return_value.raise_for_status = MagicMock()

    lead = _lead(_disposition="auto")
    hs.dispatch(lead)

    assert lead["_outreach_decision"] == "review_queue"
    assert lead["Status"] == "New"
    assert "Hunter Sequence ID" not in lead


@patch("outreach.hunter_sequences.requests.post")
def test_dispatch_hunter_api_error_falls_back_to_review(mock_post, monkeypatch):
    monkeypatch.setattr(hs, "HUNTER_SEQUENCE_ID", "sequence-abc")
    import requests as req_lib

    mock_post.return_value.raise_for_status.side_effect = req_lib.HTTPError("500")

    lead = _lead(_disposition="auto")
    hs.dispatch(lead)

    assert lead["_outreach_decision"] == "review_queue"


def test_dispatch_review_queue_calls_airtable(monkeypatch):
    monkeypatch.setattr(hs, "HUNTER_SEQUENCE_ID", "sequence-abc")
    mock_at = MagicMock()

    lead = _lead(_disposition="review")
    hs.dispatch(lead, airtable_client=mock_at)

    mock_at.add_to_manual_queue.assert_called_once()
    queued = mock_at.add_to_manual_queue.call_args[0][0]
    assert queued["Source URL"] == lead["Source URL"]
    assert queued["Status"] == "Pending"


def test_dispatch_review_queue_includes_reddit_fields(monkeypatch):
    monkeypatch.setattr(hs, "HUNTER_SEQUENCE_ID", "sequence-abc")
    mock_at = MagicMock()

    lead = _lead(
        Source="reddit",
        _disposition="review",
        **{"Reddit Username": "u/johndoe", "Subreddit": "UberDrivers"},
    )
    hs.dispatch(lead, airtable_client=mock_at)

    queued = mock_at.add_to_manual_queue.call_args[0][0]
    assert queued["Reddit Username"] == "u/johndoe"
    assert queued["Subreddit"] == "UberDrivers"


def test_dispatch_review_queue_omits_reddit_fields_for_non_reddit_leads(monkeypatch):
    monkeypatch.setattr(hs, "HUNTER_SEQUENCE_ID", "sequence-abc")
    mock_at = MagicMock()

    lead = _lead(_disposition="review")  # Source="youtube", no Reddit fields
    hs.dispatch(lead, airtable_client=mock_at)

    queued = mock_at.add_to_manual_queue.call_args[0][0]
    assert "Reddit Username" not in queued
    assert "Subreddit" not in queued


def test_dispatch_review_queue_without_airtable_does_not_raise():
    lead = _lead(_disposition="review")
    result = hs.dispatch(lead, airtable_client=None)
    assert result["_outreach_decision"] == "review_queue"


def test_dispatch_skip_does_not_call_hunter():
    lead = _lead(_disposition="discard")
    mock_at = MagicMock()
    with patch("outreach.hunter_sequences.requests.post") as mock_post:
        hs.dispatch(lead, airtable_client=mock_at)
        mock_post.assert_not_called()
    mock_at.add_to_manual_queue.assert_not_called()
    assert lead["_outreach_decision"] == "skip"
