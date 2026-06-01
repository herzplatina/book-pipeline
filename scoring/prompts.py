"""Scoring prompt templates for the Claude Haiku story evaluator."""

SYSTEM_PROMPT = (
    "You are a story evaluator for a book about human transformation. "
    "You will receive a piece of text (transcript, Reddit post, or article excerpt). "
    "Your entire response must be a single valid JSON object. "
    "Do not include markdown, code fences, commentary, or any text outside JSON. "
    "Use double quotes for every key and string value. "
    "Use null for unknown values. "
    "Return exactly these fields:\n"
    "{\n"
    '  "score": <integer 1-10>,\n'
    '  "name": <string or null — extracted full name if mentioned>,\n'
    '  "archetype": <one of: extremist, criminal, health, driver, bluecollar, other>,\n'
    '  "archetype_match": <true or false>,\n'
    '  "turning_point": <string — one sentence on the specific moment of change, or null>,\n'
    '  "summary": <string — one sentence describing the story>,\n'
    '  "contact_clue": <string or null — any email, website, or social handle mentioned>\n'
    "}\n"
    "Score 8-10: vivid, specific turning point, named individual, emotionally resonant.\n"
    "Score 5-7: clear transformation arc but vague on the turning point moment.\n"
    "Score 1-4: generic, no named individual, no specific transformation event.\n"
    "Return ONLY the JSON object. No preamble, no explanation."
)

# One-sentence context injected per archetype to sharpen Claude's evaluation lens.
ARCHETYPE_HINTS: dict[str, str] = {
    "extremist": (
        "This person left an extremist movement or hate group and rebuilt their life."
    ),
    "criminal": (
        "This person was incarcerated and successfully rebuilt their life after release."
    ),
    "health": (
        "This person overcame a serious illness, injury, or mental health crisis."
    ),
    "driver": (
        "This person worked as a gig economy driver (Uber/Lyft) and built a business or"
        " changed their life trajectory."
    ),
    "bluecollar": (
        "This person lost a blue-collar job during Covid and pivoted to"
        " entrepreneurship or a new career."
    ),
}


def build_user_message(text: str, archetype_hint: str | None = None) -> str:
    """Build the user-turn message for Claude scoring.

    Truncates content to 4 000 chars to stay within Haiku's cost-efficient range.
    """
    hint_line = f"Archetype hint: {archetype_hint}\n\n" if archetype_hint else ""
    return f"{hint_line}Content:\n{text[:4000]}"
