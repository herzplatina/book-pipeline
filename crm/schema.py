"""Shared schema constants and validation helpers for the Contacts CRM table."""

# Literal archetype values used across the pipeline
ARCHETYPES = ("extremist", "criminal", "health", "driver", "bluecollar", "other")

# CRM status progression (matches Airtable select field)
STATUSES = (
    "New",
    "Contacted",
    "Followed up",
    "Responded",
    "Pre-screened",
    "Shortlisted",
    "Declined",
    "Bounced",
)

CONTACT_METHODS = ("email", "reddit_dm", "instagram_dm", "org_intro", "linkedin")

REPLY_SENTIMENTS = ("positive", "neutral", "unsubscribe", "bounce")

# Canonical field definitions for the Contacts table.
# Values are Python types used for validation — not Airtable field types.
CONTACTS_FIELDS: dict[str, type] = {
    "Name": str,
    "First Name": str,
    "Last Name": str,
    "Archetype": str,  # one of ARCHETYPES
    "Source": str,
    "Source URL": str,
    "Channel URL": str,
    "City": str,
    "Date Window": str,
    "Interviewee Metadata": str,
    "Claude Score": int,
    "Story Summary": str,
    "Turning Point": str,
    "Email": str,
    "Email Confidence": int,
    "Contact Method": str,  # one of CONTACT_METHODS
    "Contact Value": str,
    "Requires Handcraft": bool,
    "Status": str,  # one of STATUSES
    "Hunter Lead ID": str,
    "Hunter Sequence ID": str,
    "Email Opened": bool,
    "Replied": bool,
    "Reply Sentiment": str,  # one of REPLY_SENTIMENTS
    "Pre-screen Notes": str,
    "Turning Point Answer": str,
    "Shortlisted": bool,
    "Interview Date": str,  # ISO date string
    "Consent Received": bool,
    "Created At": str,  # ISO datetime string
    "Reddit Username": str,
    "Subreddit": str,
}

# Fields required when creating a new record
REQUIRED_FIELDS = {"Source", "Source URL", "Archetype", "Status"}

# Single source of truth for which source-specific fields each discovery module
# contributes to the Manual DM Queue table, beyond the common base set.
# Only populated values are written — empty strings are never sent to Airtable.
# Add a new source here when a new discovery module is introduced.
QUEUE_SOURCE_FIELDS: dict[str, tuple[str, ...]] = {
    "youtube": ("Channel URL",),
    "reddit": ("Reddit Username", "Subreddit"),
    "listennotes": (
        "Podcast Name",
        "Episode Title",
        "Website URLs",
        "Interviewee Metadata",
    ),
    "serpapi": ("City", "Date Window"),
}


def build_queue_record(lead: dict) -> dict:
    """Build a Manual DM Queue record from a lead.

    Assembles the base fields common to all sources, then adds the populated
    source-specific fields from QUEUE_SOURCE_FIELDS. Unknown source values
    produce no extra fields. Empty values are never written to Airtable.
    """
    optional = {
        "Source URL": lead.get("Source URL", ""),
        "Archetype": lead.get("Archetype", ""),
        "Name": lead.get("Name", ""),
        "Contact Method": lead.get("Contact Method", ""),
        "Contact Value": lead.get("Contact Value", ""),
        "Notes": lead.get("Story Summary", ""),
    }
    fields: dict = {"Status": "Pending"}
    fields.update({k: v for k, v in optional.items() if v})
    for field in QUEUE_SOURCE_FIELDS.get(lead.get("Source", ""), ()):
        value = lead.get(field)
        if value:
            fields[field] = value
    return fields


def validate_lead(lead: dict) -> list[str]:
    """Returns a list of validation error strings (empty = valid)."""
    errors = []

    for field in REQUIRED_FIELDS:
        if not lead.get(field):
            errors.append(f"Missing required field: {field}")

    archetype = lead.get("Archetype")
    if archetype and archetype not in ARCHETYPES:
        errors.append(f"Invalid archetype '{archetype}' — must be one of {ARCHETYPES}")

    status = lead.get("Status")
    if status and status not in STATUSES:
        errors.append(f"Invalid status '{status}' — must be one of {STATUSES}")

    score = lead.get("Claude Score")
    if score is not None and not (1 <= int(score) <= 10):
        errors.append(f"Claude Score must be 1–10, got {score}")

    return errors


def is_handcraft_required(lead: dict) -> bool:
    """Returns True for contacts that must never be sent to Hunter Sequences."""
    archetype = lead.get("Archetype", "")
    source = lead.get("Source", "")
    status = lead.get("Status", "")

    if archetype == "extremist":
        return True
    if archetype == "criminal" and source in ("nonprofit", "org_intro"):
        return True
    if status == "Responded":
        return True

    return False
