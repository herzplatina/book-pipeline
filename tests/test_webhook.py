"""Unit tests for outreach/webhook.py — Airtable and notifications mocked."""

from unittest.mock import MagicMock, patch

from outreach.webhook import app

_TEST_SECRET = "test-secret-abc123"


def _client():
    return app.test_client()


def _post(payload, secret=_TEST_SECRET):
    """POST to /webhook/hunter with the given secret header."""
    headers = {"X-Webhook-Secret": secret} if secret is not None else {}
    return _client().post("/webhook/hunter", json=payload, headers=headers)


def _payload(event_type="reply", email="jane@example.com", sentiment="positive"):
    return {
        "type": event_type,
        "email": email,
        "reply_body": "I'd love to be interviewed!",
        "reply_category": sentiment,
    }


def _airtable_record(record_id="rec123", name="Jane Smith"):
    return {"id": record_id, "fields": {"Name": name, "Email": "jane@example.com"}}


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


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_returns_ok_on_valid_payload(mock_at):
    mock_at.return_value.find_by_email.return_value = _airtable_record()
    mock_at.return_value.update = MagicMock()

    resp = _post(_payload())

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_updates_airtable_record_on_reply(mock_at):
    mock_at.return_value.find_by_email.return_value = _airtable_record()
    mock_update = MagicMock()
    mock_at.return_value.update = mock_update

    _post(_payload(sentiment="neutral"))

    mock_update.assert_called_once_with(
        "rec123",
        {"Status": "Responded", "Replied": True, "Reply Sentiment": "neutral"},
    )


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_updates_airtable_record_on_open(mock_at):
    mock_at.return_value.find_by_email.return_value = _airtable_record()
    mock_update = MagicMock()
    mock_at.return_value.update = mock_update

    _post(_payload(event_type="open"))

    mock_update.assert_called_once_with("rec123", {"Email Opened": True})


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_updates_airtable_record_on_bounce(mock_at):
    mock_at.return_value.find_by_email.return_value = _airtable_record()
    mock_update = MagicMock()
    mock_at.return_value.update = mock_update

    _post(_payload(event_type="bounce"))

    mock_update.assert_called_once_with(
        "rec123",
        {"Status": "Bounced", "Replied": False, "Reply Sentiment": "bounce"},
    )


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_updates_airtable_record_on_unsubscribe(mock_at):
    mock_at.return_value.find_by_email.return_value = _airtable_record()
    mock_update = MagicMock()
    mock_at.return_value.update = mock_update

    _post(_payload(event_type="unsubscribe"))

    mock_update.assert_called_once_with(
        "rec123", {"Replied": True, "Reply Sentiment": "unsubscribe"}
    )


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_returns_400_when_no_email(mock_at):
    payload = {"type": "reply", "reply": {}}
    resp = _post(payload)
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_handles_unknown_lead_gracefully(mock_at):
    mock_at.return_value.find_by_email.return_value = None

    resp = _post(_payload())

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_normalises_unknown_sentiment(mock_at):
    mock_at.return_value.find_by_email.return_value = _airtable_record()
    mock_update = MagicMock()
    mock_at.return_value.update = mock_update

    _post(_payload(sentiment="not_a_real_sentiment"))

    call_fields = mock_update.call_args[0][1]
    assert call_fields["Reply Sentiment"] == "neutral"


@patch("outreach.webhook.WEBHOOK_SECRET", _TEST_SECRET)
@patch("outreach.webhook.get_client")
def test_webhook_returns_500_on_airtable_error(mock_at):
    mock_at.return_value.find_by_email.side_effect = Exception("DB error")

    resp = _post(_payload())

    assert resp.status_code == 500
    assert resp.get_json()["ok"] is False
    assert "DB error" not in resp.get_json().get("error", "")
