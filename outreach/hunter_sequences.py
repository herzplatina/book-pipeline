"""Hunter Sequences outreach dispatch.

route(lead)    -> 'hunter_sequence' | 'review_queue' | 'skip'
dispatch(lead) -> routes and fires the appropriate outreach action.
"""

import logging
from typing import TYPE_CHECKING

import requests

from config.settings import (
    HUNTER_OPENING_LINE_DEFAULT,
    HUNTER_SEQUENCE_ID,
    require_env,
)
from crm.schema import build_queue_record, is_handcraft_required

if TYPE_CHECKING:
    from crm.airtable import AirtableClient

logger = logging.getLogger(__name__)

_HUNTER_BASE = "https://api.hunter.io/v2"
_MAX_CUSTOM_VALUE_LEN = 1000


class HunterSequenceError(RuntimeError):
    """Raised when Hunter accepts the request but does not add the recipient."""


def route(lead: dict) -> str:
    """Determine outreach routing for a lead.

    Returns:
        'hunter_sequence' — email is ready; add to Hunter Sequence.
        'review_queue'    — requires human review before any send.
        'skip'            — do not contact because scoring discarded it.
    """
    if lead.get("_disposition", "discard") == "discard":
        return "skip"

    source = lead.get("Source", "")
    if source == "reddit":
        return "review_queue"

    if is_handcraft_required(lead):
        return "review_queue"

    if not lead.get("Email"):
        return "review_queue"

    if lead.get("_disposition") == "auto":
        if not HUNTER_SEQUENCE_ID:
            return "review_queue"
        return "hunter_sequence"

    return "review_queue"


def _recipient_id(result: dict) -> str:
    """Best-effort extraction of a Hunter recipient/lead identifier."""
    result = result.get("data") or result
    for key in ("id", "lead_id", "recipient_id"):
        if result.get(key):
            return str(result[key])

    recipients = result.get("recipients_added") or result.get("recipients") or []
    if isinstance(recipients, list) and recipients and isinstance(recipients[0], dict):
        for key in ("id", "lead_id", "recipient_id"):
            if recipients[0].get(key):
                return str(recipients[0][key])

    return ""


def _recipient_was_added(result: dict) -> bool:
    """Return True when Hunter reports at least one recipient was added."""
    result = result.get("data") or result
    recipients = result.get("recipients_added")
    if isinstance(recipients, list):
        return bool(recipients)
    if isinstance(recipients, int):
        return recipients > 0
    return not result.get("skipped_recipients")


def _trim_value(value: object) -> str:
    text = "" if value is None else str(value)
    return text[:_MAX_CUSTOM_VALUE_LEN]


def _sequence_custom_vars(lead: dict) -> dict[str, str]:
    """Per-lead custom variables for the Hunter Sequence payload.

    Only populated fields are included — omitting a variable is equivalent to
    an empty string in Hunter's template substitution, but keeps the payload
    clean and avoids sending unused keys for non-podcast leads.
    """
    mapping = (
        ("Podcast Name", "podcast_name"),
        ("Episode Title", "episode_title"),
        ("Website URLs", "website_urls"),
        ("Interviewee Metadata", "interviewee_metadata"),
        ("Name", "interviewee_name"),
        ("First Name", "interviewee_first_name"),
        ("Last Name", "interviewee_last_name"),
    )
    return {
        snake_key: _trim_value(lead[field])
        for field, snake_key in mapping
        if lead.get(field)
    }


def _add_to_hunter_sequence(lead: dict) -> dict:
    """POST lead to its archetype's Hunter Sequence. Mutates lead."""
    archetype = lead.get("Archetype", "")
    sequence_id = HUNTER_SEQUENCE_ID
    if not sequence_id:
        raise ValueError("No Hunter Sequence configured")

    email = lead["Email"]
    opening_line = lead.get("Story Summary") or HUNTER_OPENING_LINE_DEFAULT
    payload = {
        "emails": [email],
        "first_name": lead.get("First Name", ""),
        "last_name": lead.get("Last Name", ""),
        "opening_line": opening_line,
        "custom_variables": {
            "story_source": lead.get("Source", ""),
            "story_summary": lead.get("Story Summary", ""),
            "city": lead.get("City", ""),
            "archetype": archetype,
            **_sequence_custom_vars(lead),
        },
    }
    resp = requests.post(
        f"{_HUNTER_BASE}/campaigns/{sequence_id}/recipients",
        params={"api_key": require_env("HUNTER_KEY")},
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    if not _recipient_was_added(result):
        raise HunterSequenceError("Hunter skipped the recipient")
    lead["Hunter Lead ID"] = _recipient_id(result)
    lead["Hunter Sequence ID"] = sequence_id
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

    if decision == "hunter_sequence":
        try:
            _add_to_hunter_sequence(lead)
            logger.info("Added to Hunter Sequence: %s", lead.get("Email"))
        except (HunterSequenceError, requests.RequestException) as exc:
            logger.error("Hunter Sequence dispatch failed: %s", type(exc).__name__)
            lead["_outreach_decision"] = "review_queue"

    elif decision == "review_queue" and airtable_client is not None:
        try:
            airtable_client.add_to_manual_queue(build_queue_record(lead))
            lead["_dm_queue_written"] = True
            logger.info("Queued for review: %s", lead.get("Source URL"))
        except Exception:
            logger.exception(
                "Manual queue write failed for url=%s", lead.get("Source URL", "")
            )

    return lead
