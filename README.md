# book-pipeline

Lead discovery, scoring, enrichment, and outreach pipeline for _Why I Feel the Universe Loves Me_ — a book built on real transformation stories.

The pipeline surfaces 150–200 interview candidates across five story archetypes (extremist-to-peace-builder, formerly incarcerated, health recovery, gig-economy pivot, blue-collar Covid comeback), scores them with Claude, enriches contact info via Hunter.io, and dispatches outreach through Instantly.ai or a human review queue.

## Architecture

```
Discover → Score → Enrich → Outreach → CRM (Airtable)
```

| Stage        | What it does                                                                                                   |
| ------------ | -------------------------------------------------------------------------------------------------------------- |
| **Discover** | 5 modules: YouTube, Reddit (PRAW + Arctic Shift), SerpApi local news, nonprofits/archives, Apollo professional |
| **Score**    | Claude Haiku evaluates each lead (1–10) and extracts name, archetype, turning point, contact clues             |
| **Enrich**   | Hunter.io email waterfall (confidence ≥ 70); platform DMs for non-professional sources                         |
| **Outreach** | Instantly.ai sequences for standard archetypes; human-gated queue for Reddit DMs and sensitive contacts        |
| **CRM**      | Airtable Contacts table; Instantly webhook updates status on reply                                             |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
```

## Running

```bash
# Full pipeline
python pipeline.py

# SerpApi module only (free-tier reduced matrix, 90 calls)
python -m modules.m3_serpapi
```

## Sensitivity rules

- **Archetype: extremist** — always via org gatekeeper, never cold-contact the individual
- **Archetype: criminal + nonprofit source** — comms director intro only, offer anonymity
- **Reddit DMs** — enter human review queue; max 10/day; never auto-send

## Project structure

```
config/         API keys and discovery matrices
modules/        Discovery modules (m1–m5)
scoring/        Claude Haiku scoring engine
enrichment/     Hunter.io email finder + contact router
outreach/       Instantly, PRAW DM, manual queue
crm/            Airtable schema and client
tests/          Unit tests (all external I/O mocked)
pipeline.py     Master orchestrator
```

## Build status

Sessions completed: 1–8 (all complete) ✓
