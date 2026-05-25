"""Unit tests for outreach/webhook.py — Airtable and notifications mocked."""

from unittest.mock import MagicMock, patch

from outreach.webhook import app

_TEST_SECRET = "test-secret-abc123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client():
    return app.test_client()


def _post(payload, secret=_TEST_SECRET):
    """POST to /webhook/instantly with the given secret header."""
    headers = {"X-Webhook-Secret": secret} if secret is not None else {}
    return _client().post("/webhook/instantly", json=payload, headers=headers)


def _payload(lead_id="inst-001", email="jane@example.com", sentiment="positive"):
    return {
        "event_type": "reply_received",
        "lead": {"id": lead_id, "email": email},
        "reply": {"body": "I'd love to be interviewed!", "sentiment": sentiment},
    }


def _airtable_record(record_id="rec123", name="Jane Smith"):
    return {"id": record_id, "fields": {"Name": name, "Instantly Lead ID": "inst-001"}}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
def test_webhook_returns_401_without_secret():
    resp = _post(_payload(), secret=None)
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
def test_webhook_returns_401_with_wrong_secret():
    resp = _post(_payload(), secret="wrong-secret")
    assert resp.status_code == 401


@patch("outreach.webhook.WEBHOOK_SECRET", "")
def test_webhook_returns_401_when_secret_not_configured():
    resp = _post(_payload(), secret="anything")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /webhook/instantly — happy path
# ---------------------------------------------------------------------------


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_returns_ok_on_valid_payload(mock_at):
    mock_at.return_value.find_by_instantly_lead_id.return_value = _airtable_record()
    mock_at.return_value.update = MagicMock()

    resp = _post(_payload())

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_updates_airtable_record(mock_at):
    mock_at.return_value.find_by_instantly_lead_id.return_value = _airtable_record()
    mock_update = MagicMock()
    mock_at.return_value.update = mock_update

    _post(_payload(sentiment="neutral"))

    mock_update.assert_called_once_with(
        "rec123",
        {"Status": "Responded", "Replied": True, "Reply Sentiment": "neutral"},
    )


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_returns_400_when_no_lead_id(mock_at):
    payload = {"event_type": "reply_received", "lead": {}, "reply": {}}
    resp = _post(payload)
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_handles_unknown_lead_gracefully(mock_at):
    mock_at.return_value.find_by_instantly_lead_id.return_value = None

    resp = _post(_payload())

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_normalises_unknown_sentiment(mock_at):
    mock_at.return_value.find_by_instantly_lead_id.return_value = _airtable_record()
    mock_update = MagicMock()
    mock_at.return_value.update = mock_update

    _post(_payload(sentiment="not_a_real_sentiment"))

    call_fields = mock_update.call_args[0][1]
    assert call_fields["Reply Sentiment"] == "neutral"


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook._notify")
@patch("outreach.webhook.get_client")
def test_webhook_fires_notification_on_positive_reply(mock_at, mock_notify):
    mock_at.return_value.find_by_instantly_lead_id.return_value = _airtable_record()
    mock_at.return_value.update = MagicMock()

    _post(_payload(sentiment="positive"))

    mock_notify.assert_called_once()


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook._notify")
@patch("outreach.webhook.get_client")
def test_webhook_no_notification_on_neutral_reply(mock_at, mock_notify):
    mock_at.return_value.find_by_instantly_lead_id.return_value = _airtable_record()
    mock_at.return_value.update = MagicMock()

    _post(_payload(sentiment="neutral"))

    mock_notify.assert_not_called()


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_returns_500_on_airtable_error(mock_at):
    mock_at.return_value.find_by_instantly_lead_id.side_effect = Exception("DB error")

    resp = _post(_payload())

    assert resp.status_code == 500
    assert resp.get_json()["ok"] is False
    # Must not leak internal exception message
    assert "DB error" not in resp.get_json().get("error", "")
