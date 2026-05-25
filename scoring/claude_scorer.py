"""Claude Haiku scoring engine.

Public API
----------
score(lead)                    Module-level convenience — singleton scorer.
ClaudeScorer.score_text(text)  Score raw text, return JSON dict or None.
ClaudeScorer.score_lead(lead)  Enrich a raw lead dict in-place; return it.
get_disposition(score, match)  'auto' | 'review' | 'discard' per EDD thresholds.
"""

import json
import logging
from typing import Literal

import anthropic

from config.settings import ANTHROPIC_API_KEY
from scoring.prompts import ARCHETYPE_HINTS, SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 300

# EDD §4.2 disposition labels
Disposition = Literal["auto", "review", "discard"]


def get_disposition(score: int, archetype_match: bool) -> Disposition:
    """Map EDD scoring thresholds to a routing disposition.

    auto:    score >= 8 AND archetype_match=True  → proceed to enrichment
    review:  score 6-7, or score >= 8 with archetype_match=False → human gate
    discard: score <= 5                            → do not enrich or contact
    """
    if score <= 5:
        return "discard"
    if score >= 8 and archetype_match:
        return "auto"
    return "review"


class ClaudeScorer:
    """Wraps an Anthropic client to score lead content via Claude Haiku."""

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

    def score_text(
        self,
        text: str,
        archetype_hint: str | None = None,
    ) -> dict | None:
        """Score raw text string. Returns parsed JSON dict or None on failure."""
        if not text.strip():
            return None
        user_msg = build_user_message(text, archetype_hint)
        try:
            response = self._client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            return json.loads(response.content[0].text)
        except (json.JSONDecodeError, anthropic.APIError) as exc:
            logger.warning("Scoring failed: %s", exc)
            return None

    def score_lead(self, lead: dict) -> dict:
        """Enrich a raw lead dict with Claude scoring fields. Mutates and returns lead.

        Reads ``_content`` from the lead for the text to score.
        Sets ``Claude Score``, ``Story Summary``, ``Turning Point``,
        ``Name`` / ``First Name`` / ``Last Name`` (if not already present),
        and private ``_contact_clue``, ``_archetype_match``, ``_disposition``.
        """
        content = lead.get("_content", "")
        archetype = lead.get("Archetype")
        archetype_hint = ARCHETYPE_HINTS.get(archetype) if archetype else None

        scoring = self.score_text(content, archetype_hint)
        if scoring is None:
            lead["_disposition"] = "discard"
            return lead

        score = int(scoring.get("score", 0))
        name = scoring.get("name") or ""
        archetype_match = bool(scoring.get("archetype_match"))
        name_parts = name.split(" ", 1) if name else []

        lead["Claude Score"] = score
        lead["Story Summary"] = scoring.get("summary")
        lead["Turning Point"] = scoring.get("turning_point")
        lead["_contact_clue"] = scoring.get("contact_clue")
        lead["_archetype_match"] = archetype_match
        lead["_disposition"] = get_disposition(score, archetype_match)

        # Discover modules may have already set Name (e.g. from Apollo); don't overwrite.
        if not lead.get("Name") and name:
            lead["Name"] = name
        if not lead.get("First Name") and name_parts:
            lead["First Name"] = name_parts[0]
        if not lead.get("Last Name") and len(name_parts) > 1:
            lead["Last Name"] = name_parts[1]

        return lead


# ---------------------------------------------------------------------------
# Module-level singleton — matches the orchestrator call pattern:
#   scored = [claude_scorer.score(lead) for lead in all_raw_leads]
# ---------------------------------------------------------------------------

_scorer: ClaudeScorer | None = None


def _get_scorer() -> ClaudeScorer:
    global _scorer
    if _scorer is None:
        _scorer = ClaudeScorer(ANTHROPIC_API_KEY)
    return _scorer


def score(lead: dict) -> dict:
    """Score a lead using the module-level singleton scorer."""
    return _get_scorer().score_lead(lead)
