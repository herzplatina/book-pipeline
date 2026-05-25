"""Hunter.io email enrichment — waterfall strategy.

enrich(lead) mutates the lead dict in-place and returns it.
Sets Email, Email Confidence, Contact Method, Contact Value.
"""

import logging
import re
from urllib.parse import urlparse

import requests

from config.settings import HUNTER_CONFIDENCE_MIN, HUNTER_KEY

logger = logging.getLogger(__name__)

_HUNTER_BASE = "https://api.hunter.io/v2"
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def _extract_email_from_clue(clue: str) -> str | None:
    match = _EMAIL_RE.search(clue or "")
    return match.group(0) if match else None


def _domain_from_url(url: str) -> str | None:
    """Return bare domain (e.g. 'example.com') from a URL string, or None."""
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        host = urlparse(url).netloc
        host = re.sub(r"^www\.", "", host)
        if "." in host and " " not in host and "@" not in host:
            return host
    except ValueError:
        pass
    return None


def _hunter_email_finder(
    domain: str, first_name: str, last_name: str
) -> tuple[str, int] | None:
    """Call Hunter email-finder. Returns (email, confidence) or None."""
    try:
        resp = requests.get(
            f"{_HUNTER_BASE}/email-finder",
            params={
                "domain": domain,
                "first_name": first_name,
                "last_name": last_name,
                "api_key": HUNTER_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        email = data.get("email")
        confidence = data.get("score", 0)
        if email and confidence >= HUNTER_CONFIDENCE_MIN:
            return email, confidence
    except requests.HTTPError as exc:
        logger.warning("Hunter email-finder failed: %s", exc)
    return None


def _hunter_domain_search(domain: str) -> tuple[str, int] | None:
    """Call Hunter domain-search. Returns highest-confidence (email, score) or None."""
    try:
        resp = requests.get(
            f"{_HUNTER_BASE}/domain-search",
            params={"domain": domain, "limit": 10, "api_key": HUNTER_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        emails = resp.json().get("data", {}).get("emails", [])
        qualified = [
            (e["value"], e.get("confidence", 0))
            for e in emails
            if e.get("value") and e.get("confidence", 0) >= HUNTER_CONFIDENCE_MIN
        ]
        if qualified:
            return max(qualified, key=lambda t: t[1])
    except requests.HTTPError as exc:
        logger.warning("Hunter domain-search failed: %s", exc)
    return None


def enrich(lead: dict) -> dict:
    """Run Hunter.io waterfall enrichment on a scored lead. Mutates and returns lead.

    Waterfall:
    1. Direct email in _contact_clue → use as-is (confidence 100).
    2. Domain from _contact_clue + name → Hunter email-finder.
    3. Domain from Source URL + name   → Hunter email-finder.
    4. Domain from either source        → Hunter domain-search fallback.
    """
    clue = lead.get("_contact_clue") or ""
    first = lead.get("First Name") or ""
    last = lead.get("Last Name") or ""

    direct_email = _extract_email_from_clue(clue)
    if direct_email:
        lead["Email"] = direct_email
        lead["Email Confidence"] = 100
        lead["Contact Method"] = "email"
        lead["Contact Value"] = direct_email
        logger.debug("Direct email from clue: %s", direct_email)
        return lead

    clue_domain = _domain_from_url(clue) if clue else None
    source_domain = _domain_from_url(lead.get("Source URL") or "")
    domain = clue_domain or source_domain

    if not domain:
        logger.debug("No domain found for %s", lead.get("Source URL", ""))
        return lead

    if first and last:
        result = _hunter_email_finder(domain, first, last)
        if result:
            email, confidence = result
            lead["Email"] = email
            lead["Email Confidence"] = confidence
            lead["Contact Method"] = "email"
            lead["Contact Value"] = email
            logger.debug("Hunter email-finder → %s (%d%%)", email, confidence)
            return lead

    result = _hunter_domain_search(domain)
    if result:
        email, confidence = result
        lead["Email"] = email
        lead["Email Confidence"] = confidence
        lead["Contact Method"] = "email"
        lead["Contact Value"] = email
        logger.debug("Hunter domain-search → %s (%d%%)", email, confidence)

    return lead
