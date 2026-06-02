# book-pipeline

Lead discovery, scoring, enrichment, and outreach pipeline for _Why I Feel the Universe Loves Me_ — a book built on real transformation stories.

The pipeline surfaces 150–200 interview candidates across five story archetypes (extremist-to-peace-builder, formerly incarcerated, health recovery, gig-economy pivot, blue-collar Covid comeback), scores them with Claude, enriches contact info via Hunter.io, and dispatches outreach through Hunter Sequences or a human review queue.

Current operating scope: Apollo, Apify, and nonprofit/archive scraping are paused. Default runs use SerpApi, YouTube, Reddit, and ListenNotes while the lead strategy is narrowed. Apify will be revisited later as a possible shared scraping backend.

## Architecture

```
Discover → Score → Enrich → Outreach → CRM (Airtable)
```

| Stage        | What it does                                                                                                   |
| ------------ | -------------------------------------------------------------------------------------------------------------- |
| **Discover** | Active sources: SerpApi local news, YouTube, Reddit (PRAW + Arctic Shift), and ListenNotes. Apollo/Apify/nonprofit scraping remain paused for later. |
| **Score**    | Claude Haiku evaluates each lead (1–10) and extracts name, archetype, turning point, contact clues             |
| **Enrich**   | Hunter.io email waterfall (confidence ≥ 70); platform DMs for non-professional sources                         |
| **Outreach** | Hunter Sequences for standard archetypes; human-gated queue for Reddit DMs and sensitive contacts             |
| **CRM**      | Airtable Contacts table; Hunter webhook updates status on reply                                                |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
```

## Running

```bash
# Default active pipeline: SerpApi, YouTube, Reddit, ListenNotes
python pipeline.py

# Explicit module runs
python pipeline.py --modules serpapi youtube reddit listennotes
python -m modules.m3_serpapi
python -m modules.runner listennotes
```

## Sensitivity rules

- **Archetype: extremist** — always via org gatekeeper, never cold-contact the individual
- **Archetype: criminal + nonprofit source** — paused for now; when re-enabled, use comms director intro only and offer anonymity
- **Reddit DMs** — enter human review queue; max 10/day; never auto-send

## Project structure

```
config/         API keys and discovery matrices
modules/        Discovery modules; active defaults are SerpApi, YouTube, Reddit, ListenNotes
scoring/        Claude Haiku scoring engine
enrichment/     Hunter.io email finder + contact router
outreach/       Hunter Sequences, PRAW DM, manual queue
crm/            Airtable schema and client
tests/          Unit tests (all external I/O mocked)
pipeline.py     Master orchestrator
```

## Build status

Sessions completed: 1–8 (all complete) ✓
