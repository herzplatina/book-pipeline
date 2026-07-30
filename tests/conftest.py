"""Stub all required environment variables so settings.py loads without a real .env."""

import os

_REQUIRED_STUBS = {
    "YOUTUBE_API_KEY": "stub",
    "SERPAPI_KEY": "stub",
    "LISTENNOTES_KEY": "stub",
    "APOLLO_KEY": "stub",
    "ANTHROPIC_API_KEY": "stub",
    "HUNTER_KEY": "stub",
    "AIRTABLE_PAT": "stub",
    "AIRTABLE_BASE_ID": "stub",
}

for key, val in _REQUIRED_STUBS.items():
    # Not setdefault: GitHub Actions injects an *empty string* for a job-level
    # env var whose secret is not configured, so the key exists and setdefault
    # would leave the stub unapplied. Treat empty as unset -- these tests mock
    # every HTTP call and must never depend on real credentials.
    if not os.environ.get(key):
        os.environ[key] = val
