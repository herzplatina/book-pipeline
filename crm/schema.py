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
    "City": str,
    "Date Window": str,
    "Claude Score": int,
    "Story Summary": str,
    "Turning Point": str,
    "Email": str,
    "Email Confidence": int,
    "Contact Method": str,  # one of CONTACT_METHODS
    "Contact Value": str,
    "Requires Handcraft": bool,
    "Status": str,  # one of STATUSES
    "Instantly Lead ID": str,
    "Replied": bool,
    "Reply Sentiment": str,  # one of REPLY_SENTIMENTS
    "Pre-screen Notes": str,
    "Turning Point Answer": str,
    "Shortlisted": bool,
    "Interview Date": str,  # ISO date string
    "Consent Received": bool,
    "Created At": str,  # ISO datetime string
}

# Fields required when creating a new record
REQUIRED_FIELDS = {"Source", "Source URL", "Archetype", "Status"}


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
    """Returns True for contacts that must never be sent to Instantly."""
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
