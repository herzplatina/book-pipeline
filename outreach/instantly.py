"""Instantly.ai outreach dispatch.

route(lead)    → 'instantly' | 'review_queue' | 'skip'
dispatch(lead) → routes and fires the appropriate outreach action.
"""

import logging
from typing import TYPE_CHECKING

import requests

from config.settings import (
    INSTANTLY_CAMPAIGNS,
    INSTANTLY_OPENING_LINE_DEFAULT,
    require_env,
)
from crm.schema import is_handcraft_required

if TYPE_CHECKING:
    from crm.airtable import AirtableClient

logger = logging.getLogger(__name__)

_INSTANTLY_BASE = "https://api.instantly.ai/api/v1"


def route(lead: dict) -> str:
    """Determine outreach routing for a lead.

    Returns:
        'instantly'    — email is ready; send to Instantly campaign.
        'review_queue' — requires human review before any send.
        'skip'         — do not contact (sensitivity rule or discard score).
    """
    if lead.get("_disposition", "discard") == "discard":
        return "skip"

    archetype = lead.get("Archetype", "")
    source = lead.get("Source", "")

    # Hard sensitivity rules (README §Sensitivity rules)
    if archetype == "extremist":
        return "skip"
    if archetype == "criminal" and source in ("nonprofit", "org_intro"):
        return "skip"
    if source == "reddit":
        return "review_queue"

    if is_handcraft_required(lead):
        return "review_queue"

    if not lead.get("Email"):
        return "review_queue"

    if lead.get("_disposition") == "auto":
        if not INSTANTLY_CAMPAIGNS.get(archetype):
            return "review_queue"
        return "instantly"

    return "review_queue"


def _add_to_instantly(lead: dict) -> dict:
    """POST lead to its archetype's Instantly campaign. Mutates lead."""
    archetype = lead.get("Archetype", "")
    campaign_id = INSTANTLY_CAMPAIGNS.get(archetype, "")
    if not campaign_id:
        raise ValueError(
            f"No Instantly campaign configured for archetype '{archetype}'"
        )

    payload = {
        "api_key": require_env("INSTANTLY_KEY"),
        "campaign_id": campaign_id,
        "email": lead["Email"],
        "first_name": lead.get("First Name", ""),
        "last_name": lead.get("Last Name", ""),
        "personalization": lead.get("Story Summary") or INSTANTLY_OPENING_LINE_DEFAULT,
    }
    resp = requests.post(f"{_INSTANTLY_BASE}/lead/add", json=payload, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    lead["Instantly Lead ID"] = result.get("id", "")
    lead["Status"] = "Contacted"
    return lead


def dispatch(lead: dict, airtable_client: "AirtableClient | None" = None) -> dict:
    """Route and dispatch outreach for a lead. Mutates and returns lead.

    Args:
        lead:            A scored + enriched lead dict.
        airtable_client: Optional AirtableClient; if provided, review_queue
                         leads are written to the Manual DM Queue table.
    """
    decision = route(lead)
    lead["_outreach_decision"] = decision

    if decision == "instantly":
        try:
            _add_to_instantly(lead)
            logger.info("Dispatched to Instantly: %s", lead.get("Email"))
        except requests.HTTPError as exc:
            logger.error("Instantly dispatch failed: %s", exc)
            lead["_outreach_decision"] = "review_queue"

    elif decision == "review_queue" and airtable_client is not None:
        try:
            airtable_client.add_to_manual_queue(
                {
                    "Source URL": lead.get("Source URL", ""),
                    "Archetype": lead.get("Archetype", ""),
                    "Name": lead.get("Name", ""),
                    "Contact Method": lead.get("Contact Method", ""),
                    "Contact Value": lead.get("Contact Value", ""),
                    "Status": "Pending",
                    "Notes": lead.get("Story Summary", ""),
                }
            )
            logger.info("Queued for review: %s", lead.get("Source URL"))
        except Exception:
            logger.exception(
                "Manual queue write failed for url=%s", lead.get("Source URL", "")
            )

    return lead
