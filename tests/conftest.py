"""Stub all required environment variables so settings.py loads without a real .env."""

import os

_REQUIRED_STUBS = {
    "YOUTUBE_API_KEY": "stub",
    "REDDIT_CLIENT_ID": "stub",
    "REDDIT_CLIENT_SECRET": "stub",
    "REDDIT_USER_AGENT": "stub",
    "SERPAPI_KEY": "stub",
    "LISTENNOTES_KEY": "stub",
    "APOLLO_KEY": "stub",
    "ANTHROPIC_API_KEY": "stub",
    "HUNTER_KEY": "stub",
    "INSTANTLY_KEY": "stub",
    "AIRTABLE_PAT": "stub",
    "AIRTABLE_BASE_ID": "stub",
}

for key, val in _REQUIRED_STUBS.items():
    os.environ.setdefault(key, val)
