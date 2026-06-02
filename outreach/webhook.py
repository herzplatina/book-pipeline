"""Flask webhook receiver for Hunter Sequences notifications.

Mount this app or register its blueprint in a WSGI server.
Hunter must be configured to POST to: POST /webhook/hunter

Expected payload shape:
    {
        "type": "reply|open|bounce|unsubscribe|completed",
        "email": "lead@example.com",
        "reply_category": "positive|neutral|unsubscribe|bounce"
    }

Authentication: every request must include the header
    X-Webhook-Secret: <WEBHOOK_SECRET from .env>
"""

import hmac
import logging

from flask import Flask, jsonify, request

from config.settings import WEBHOOK_SECRET
from crm.airtable import get_client
from crm.schema import REPLY_SENTIMENTS

logger = logging.getLogger(__name__)

app = Flask(__name__)


def _verify_secret(req) -> bool:
    """Return True only when the request carries the correct webhook secret."""
    if not WEBHOOK_SECRET:
        logger.warning("WEBHOOK_SECRET is not set — all requests will be rejected")
        return False
    provided = req.headers.get("X-Webhook-Secret", "")
    return hmac.compare_digest(provided, WEBHOOK_SECRET)


def _event_type(data: dict) -> str:
    raw = str(data.get("type") or data.get("event_type") or "").lower()
    if raw in ("reply", "replied", "email_replied", "reply_received"):
        return "reply"
    if raw in ("open", "opened", "email_opened"):
        return "open"
    if raw in ("bounce", "bounced", "email_bounced"):
        return "bounce"
    if raw in ("unsubscribe", "unsubscribed", "email_unsubscribed"):
        return "unsubscribe"
    if raw in ("completed", "sequence_completed"):
        return "completed"
    return raw


def _lead_email(data: dict) -> str:
    lead = data.get("lead") or {}
    recipient = data.get("recipient") or {}
    return str(data.get("email") or lead.get("email") or recipient.get("email") or "")


def _reply_sentiment(data: dict, event_type: str) -> str:
    reply = data.get("reply") or {}
    sentiment = str(
        data.get("reply_category") or data.get("sentiment") or reply.get("sentiment")
    )
    sentiment = sentiment.lower() if sentiment else "neutral"
    if event_type == "bounce":
        return "bounce"
    if event_type == "unsubscribe":
        return "unsubscribe"
    return sentiment if sentiment in REPLY_SENTIMENTS else "neutral"


@app.route("/webhook/hunter", methods=["POST"])
def hunter_webhook():
    """Handle a Hunter Sequences webhook and update Airtable."""
    if not _verify_secret(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}

    event_type = _event_type(data)
    email = _lead_email(data)
    sentiment = _reply_sentiment(data, event_type)

    if not email:
        logger.warning("Webhook received with no email")
        return jsonify({"ok": False, "error": "missing email"}), 400

    try:
        client = get_client()
        record = client.find_by_email(email)
        if record:
            fields = {}
            if event_type == "open":
                fields["Email Opened"] = True
            elif event_type == "bounce":
                fields.update(
                    {"Status": "Bounced", "Replied": False, "Reply Sentiment": "bounce"}
                )
            elif event_type == "reply":
                fields.update(
                    {
                        "Status": "Responded",
                        "Replied": True,
                        "Reply Sentiment": sentiment,
                    }
                )
            elif event_type == "unsubscribe":
                fields.update({"Replied": True, "Reply Sentiment": "unsubscribe"})
            elif event_type == "completed":
                fields["Status"] = "Declined"

            if fields:
                client.update(record["id"], fields)
                logger.info("Updated record for Hunter event %s → %s", email, fields)
        else:
            logger.warning("No Airtable record found for Hunter email: %s", email)
    except Exception:
        logger.exception("Webhook handler error")
        return jsonify({"ok": False, "error": "internal error"}), 500

    return jsonify({"ok": True})
