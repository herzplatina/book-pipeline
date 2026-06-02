"""Environment-driven configuration for the book pipeline.

All values are read from environment variables (loaded from .env via dotenv).
Call require_env() at the integration boundary so module imports stay cheap and
module-specific smoke tests only require the credentials they actually use.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def require_env(key: str) -> str:
    """Return an environment variable or raise a clear configuration error."""
    val = os.environ.get(key)
    if not val:
        raise EnvironmentError(f"Missing required environment variable: {key}")
    return val


# Required credentials are intentionally loaded lazily via require_env().
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# --- Scoring Thresholds ---
CLAUDE_SCORE_THRESHOLD = int(os.environ.get("CLAUDE_SCORE_THRESHOLD", "7"))
HUNTER_CONFIDENCE_MIN = int(os.environ.get("HUNTER_CONFIDENCE_MIN", "70"))
SERPAPI_SLEEP_SECONDS = float(os.environ.get("SERPAPI_SLEEP_SECONDS", "1.2"))
YOUTUBE_SLEEP_SECONDS = float(os.environ.get("YOUTUBE_SLEEP_SECONDS", "0.5"))
REDDIT_SLEEP_SECONDS = float(os.environ.get("REDDIT_SLEEP_SECONDS", "1.0"))
NONPROFIT_SLEEP_SECONDS = float(os.environ.get("NONPROFIT_SLEEP_SECONDS", "1.0"))
APOLLO_SLEEP_SECONDS = float(os.environ.get("APOLLO_SLEEP_SECONDS", "1.0"))

# --- Discovery: YouTube ---
YOUTUBE_SEARCH_QUERIES = {
    "health": [
        "Joe Dispenza healing miracle",
        "spontaneous remission story",
        "healed from cancer story",
        "mental health recovery transformation",
    ],
    "driver": [
        "Uber driver entrepreneur story",
        "gig worker building business",
        "driving for Uber while building startup",
    ],
    "criminal": [
        "life after prison success",
        "reformed criminal entrepreneur",
        "formerly incarcerated second chance story",
    ],
}

YOUTUBE_FILTERS = {
    "videoDuration": "medium",  # 4–20 min
    "type": "video",
    "maxResults": 50,
    "order": "relevance",
}

# --- Discovery: Reddit ---
SUBREDDITS = {
    "driver": ["UberDrivers", "lyftdrivers", "gig_economy"],
    "criminal": ["offmychest", "reentry", "excons"],
    "health": ["addiction", "Recovery", "CPTSD", "offmychest"],
    "bluecollar": ["AskWorkplace", "jobs", "careerguidance"],
}

REDDIT_KEYWORDS = [
    "started a business",
    "entrepreneur",
    "built something",
    "second chance",
    "turned my life around",
    "got out and",
    "healed from",
    "sober and now",
    "lost my job and",
]

REDDIT_FILTERS = {
    "min_score": 100,
    "time_filter": "year",
    "limit": 100,
}

ARCTIC_SHIFT_DATE_RANGE = {
    "after": "2020-01-01",
    "before": "2023-12-31",
}

# --- Discovery: SerpApi ---
CITIES = [
    ("Detroit, Michigan, United States", ["detroitnews.com", "freep.com", "mlive.com"]),
    (
        "Pittsburgh, Pennsylvania, United States",
        ["post-gazette.com", "wesa.fm", "triblive.com"],
    ),
    (
        "Cleveland, Ohio, United States",
        ["cleveland.com", "crainscleveland.com", "ideastream.org"],
    ),
    (
        "Tulsa, Oklahoma, United States",
        ["tulsaworld.com", "tulsapeople.com", "kjrh.com"],
    ),
    (
        "Louisville, Kentucky, United States",
        ["courier-journal.com", "wdrb.com", "louisvillemag.com"],
    ),
    (
        "Memphis, Tennessee, United States",
        ["commercialappeal.com", "dailymemphian.com", "wreg.com"],
    ),
    ("Fresno, California, United States", ["fresnobee.com", "kvpr.org", "abc30.com"]),
    (
        "El Paso, Texas, United States",
        ["elpasotimes.com", "kvia.com", "elpasomatters.org"],
    ),
]

DATE_WINDOWS = [
    ("1/1/2020", "6/30/2020", "early_covid"),
    ("7/1/2020", "12/31/2020", "late_covid"),
    ("1/1/2021", "6/30/2021", "rebuild_early"),  # PRIORITY
    ("7/1/2021", "12/31/2021", "rebuild_peak"),  # PRIORITY
    ("1/1/2022", "12/31/2022", "established"),
    ("1/1/2023", "12/31/2023", "lookback"),
]

QUERY_TERMS = [
    '"lost job" "Covid" "started"',
    '"laid off" "pandemic" "built"',
    '"Covid" "layoff" "comeback"',
    '"lost everything" "Covid" "now"',
    '"pandemic" "unemployed" "entrepreneur"',
    '"furloughed" "Covid" "new business"',
]

# --- Discovery: Nonprofits ---
NONPROFIT_URLS = [
    "https://defyventures.org/alumni-stories/",
    "https://www.prisonfellowship.org/stories/",
    "https://thedoefund.org/stories/",
    "https://lifeafterhate.org/our-team/",
    "https://moonshotcve.com/people/",
    "https://cleanslate.org/stories/",
]

LISTENNOTES_QUERIES = [
    "former prisoner entrepreneur",
    "Joe Dispenza healing story",
    "Covid job loss rebuilt life",
    "deradicalization story",
    "addiction recovery second career",
]

# --- Discovery: Apollo ---
APOLLO_SEARCH_PAYLOAD = {
    "api_key": "",  # injected at runtime from APOLLO_KEY
    "q_organization_industry_tag_ids": [
        "manufacturing",
        "construction",
        "transportation",
        "hospitality",
        "retail",
        "food_and_beverage",
    ],
    "employment_history": {
        "end_date_range": {"min": "2020-01-01", "max": "2021-06-30"},
        "current": False,
    },
    "q_keywords": "founder OR owner OR started OR built OR launched",
    "page": 1,
    "per_page": 50,
}

# --- Outreach: Hunter Sequence ID ---
# Fill this in once the sequence is created in Hunter dashboard.
HUNTER_SEQUENCE_ID = os.environ.get("HUNTER_SEQUENCE_ID", "")

HUNTER_OPENING_LINE_DEFAULT = (
    "I came across your story and was genuinely moved by what you've been through."
)
