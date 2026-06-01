"""Apollo.io professional discovery module — Archetype: bluecollar.

Searches for people who left blue-collar industries during Covid and
launched businesses, using Apollo's people search API.

discover() returns raw leads with _content and pre-populated name/email fields.
Scoring is handled downstream by scoring.claude_scorer.
"""

import copy
import logging
import time

import requests

from config.settings import APOLLO_SEARCH_PAYLOAD, APOLLO_SLEEP_SECONDS, require_env

logger = logging.getLogger(__name__)

_APOLLO_BASE = "https://api.apollo.io/v1"

# Max pages to paginate (50 results/page × 3 pages = 150 leads max)
_MAX_PAGES = 3


def _apollo_search(page: int) -> list[dict]:
    """Call Apollo mixed_people/search for one page. Returns raw person dicts."""
    payload = copy.deepcopy(APOLLO_SEARCH_PAYLOAD)
    payload["api_key"] = require_env("APOLLO_KEY")
    payload["page"] = page
    try:
        resp = requests.post(
            f"{_APOLLO_BASE}/mixed_people/search",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("people", [])
    except requests.HTTPError as exc:
        logger.warning("Apollo search failed (page %d): %s", page, exc)
        return []


def _build_lead(person: dict) -> dict | None:
    """Convert an Apollo person dict to a raw lead. Returns None if unusable."""
    email = person.get("email", "")
    first = person.get("first_name", "")
    last = person.get("last_name", "")
    name = f"{first} {last}".strip()
    if not name:
        return None

    # Build _content from employment history + headline
    headline = person.get("headline", "")
    title = person.get("title", "")
    org = person.get("organization", {}).get("name", "")
    employment_lines = []
    for emp in person.get("employment_history", [])[:4]:
        emp_title = emp.get("title", "")
        emp_org = emp.get("organization_name", "")
        emp_start = emp.get("start_date", "")
        emp_end = emp.get("end_date", "current")
        if emp_title or emp_org:
            employment_lines.append(f"{emp_title} at {emp_org} ({emp_start}–{emp_end})")

    parts = [p for p in (headline, title, org, "\n".join(employment_lines)) if p]
    content = "\n\n".join(parts)

    lead: dict = {
        "Archetype": "bluecollar",
        "Source": "apollo",
        "Source URL": person.get("linkedin_url", "")
        or f"https://app.apollo.io/#/people/{person.get('id', '')}",
        "Status": "New",
        "Name": name,
        "First Name": first,
        "Last Name": last,
        "_content": content,
        "_apollo_id": person.get("id", ""),
    }

    if email:
        lead["Email"] = email
        lead["Email Confidence"] = person.get("email_confidence_cd", 0) or 0
        lead["Contact Method"] = "email"
        lead["Contact Value"] = email

    return lead


def discover(max_pages: int = _MAX_PAGES) -> list[dict]:
    """Search Apollo for blue-collar Covid pivot leads. Returns raw leads.

    Returns:
        All unique leads with ``_content`` set. Scoring and threshold filtering
        are handled downstream by ``scoring.claude_scorer`` and the orchestrator.
    """
    seen_ids: set[str] = set()
    leads: list[dict] = []

    for page in range(1, max_pages + 1):
        logger.info("Apollo search page %d/%d", page, max_pages)
        people = _apollo_search(page)
        if not people:
            logger.info("No more results at page %d", page)
            break

        for person in people:
            apollo_id = person.get("id", "")
            if apollo_id and apollo_id in seen_ids:
                continue
            if apollo_id:
                seen_ids.add(apollo_id)

            lead = _build_lead(person)
            if lead:
                leads.append(lead)

        time.sleep(APOLLO_SLEEP_SECONDS)

    logger.info("Discovery complete: %d Apollo leads", len(leads))
    return leads


if __name__ == "__main__":
    from modules.runner import run

    run(discover, detail_field="Email", detail_width=35, url_width=50)
