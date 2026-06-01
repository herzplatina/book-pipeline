"""Flask webhook receiver for Instantly.ai reply notifications.

Mount this app or register its blueprint in a WSGI server.
Instantly must be configured to POST to: POST /webhook/instantly

Expected payload shape:
    {
        "event_type": "reply_received",
        "lead": {"id": "<Instantly Lead ID>", "email": "..."},
        "reply": {"body": "...", "sentiment": "positive|neutral|unsubscribe|bounce"}
    }

Authentication: every request must include the header
    X-Webhook-Secret: <WEBHOOK_SECRET from .env>
"""

import hmac
import logging

import requests
from flask import Flask, jsonify, request

from config.settings import NOTIFY_EMAIL, SLACK_WEBHOOK_URL, WEBHOOK_SECRET
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


def _notify(lead_name: str, email: str, summary: str) -> None:
    """Fire a Slack or email notification for a positive reply."""
    msg = f"Positive reply from {lead_name} ({email}): {summary[:120]}"
    if SLACK_WEBHOOK_URL:
        try:
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, timeout=5)
        except Exception:
            logger.exception("Slack notify failed")
    if NOTIFY_EMAIL:
        # TODO: b/0 - implement email notification for positive replies
        logger.debug("Email notification not yet implemented; target=%s", NOTIFY_EMAIL)


@app.route("/webhook/instantly", methods=["POST"])
def instantly_reply():
    """Handle an Instantly reply webhook and update Airtable."""
    if not _verify_secret(request):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}

    lead_id = (data.get("lead") or {}).get("id", "")
    email = (data.get("lead") or {}).get("email", "")
    reply = data.get("reply") or {}
    sentiment = reply.get("sentiment", "neutral")

    if sentiment not in REPLY_SENTIMENTS:
        sentiment = "neutral"

    if not lead_id:
        logger.warning("Webhook received with no lead_id")
        return jsonify({"ok": False, "error": "missing lead_id"}), 400

    try:
        client = get_client()
        record = client.find_by_instantly_lead_id(lead_id)
        if record:
            client.update(
                record["id"],
                {
                    "Status": "Responded",
                    "Replied": True,
                    "Reply Sentiment": sentiment,
                },
            )
            logger.info("Updated record for lead %s → %s", lead_id, sentiment)
            if sentiment == "positive":
                name = record.get("fields", {}).get("Name", email)
                summary = reply.get("body", "")
                _notify(name, email, summary)
        else:
            logger.warning(
                "No Airtable record found for Instantly Lead ID: %s", lead_id
            )
    except Exception:
        logger.exception("Webhook handler error")
        return jsonify({"ok": False, "error": "internal error"}), 500

    return jsonify({"ok": True})
