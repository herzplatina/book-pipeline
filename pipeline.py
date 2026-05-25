"""Master pipeline orchestrator.

Runs all discovery modules → scores with Claude → enriches via Hunter.io
→ dispatches via Instantly.ai or human review queue → upserts to Airtable.

Usage:
    python pipeline.py                    # full run, all modules
    python pipeline.py --modules youtube serpapi   # specific modules only
"""

import argparse
import logging
import sys

from config.settings import CLAUDE_SCORE_THRESHOLD
from crm.airtable import get_client
from enrichment.hunter import enrich
from modules import m1_youtube, m2_reddit, m3_serpapi, m4_nonprofits, m5_apollo
from outreach.instantly import dispatch
from scoring.claude_scorer import score

logger = logging.getLogger(__name__)

# Registry of all discovery modules by short name
MODULES: dict = {
    "youtube": m1_youtube,
    "reddit": m2_reddit,
    "serpapi": m3_serpapi,
    "nonprofits": m4_nonprofits,
    "apollo": m5_apollo,
}


def run(module_names: list[str] | None = None) -> dict:
    """Run the pipeline end-to-end. Returns a summary dict.

    Args:
        module_names: List of module keys from MODULES to run.
                      Defaults to all modules when None.

    Returns:
        Summary with keys: discovered, qualifying, dispatched,
        review_queue, skipped, errors.
    """
    names = module_names or list(MODULES.keys())
    airtable = get_client()

    # --- Stage 1: Discover ---
    all_raw: list[dict] = []
    for name in names:
        module = MODULES[name]
        logger.info("Discovering via %s...", name)
        try:
            leads = module.discover()
            logger.info("  %s: %d raw leads", name, len(leads))
            all_raw.extend(leads)
        except Exception as exc:
            logger.error("Discovery failed for %s: %s", name, exc)

    logger.info("Total raw leads: %d", len(all_raw))

    # --- Stage 2: Score ---
    scored: list[dict] = []
    for lead in all_raw:
        try:
            scored.append(score(lead))
        except Exception as exc:
            logger.error("Scoring failed for %s: %s", lead.get("Source URL", "?"), exc)

    # --- Stage 3: Filter ---
    qualifying = [
        lead
        for lead in scored
        if (lead.get("Claude Score") or 0) >= CLAUDE_SCORE_THRESHOLD
    ]
    logger.info(
        "Qualifying leads (score >= %d): %d / %d",
        CLAUDE_SCORE_THRESHOLD,
        len(qualifying),
        len(scored),
    )

    # --- Stage 4: Enrich ---
    for lead in qualifying:
        try:
            enrich(lead)
        except Exception as exc:
            logger.error(
                "Enrichment failed for %s: %s", lead.get("Source URL", "?"), exc
            )

    # --- Stage 5: Dispatch + CRM upsert ---
    # _outreach_decision values from dispatch(): "instantly", "review_queue", "skip"
    _decision_key = {"instantly": "dispatched", "skip": "skipped"}
    counts = {"dispatched": 0, "review_queue": 0, "skipped": 0, "errors": 0}
    for lead in qualifying:
        try:
            dispatch(lead, airtable_client=airtable)
            raw = lead.get("_outreach_decision", "skip")
            key = _decision_key.get(raw, raw)
            if key in counts:
                counts[key] += 1
        except Exception as exc:
            logger.error("Dispatch failed for %s: %s", lead.get("Source URL", "?"), exc)
            counts["errors"] += 1

        try:
            airtable.upsert(lead)
        except Exception as exc:
            logger.error(
                "Airtable upsert failed for %s: %s", lead.get("Source URL", "?"), exc
            )
            counts["errors"] += 1

    summary = {
        "discovered": len(all_raw),
        "scored": len(scored),
        "qualifying": len(qualifying),
        **counts,
    }
    logger.info("Pipeline complete: %s", summary)
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the book-pipeline.")
    parser.add_argument(
        "--modules",
        nargs="+",
        choices=list(MODULES.keys()),
        metavar="MODULE",
        help="Modules to run (default: all). Choices: " + ", ".join(MODULES.keys()),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    result = run(args.modules)
    print("\n=== Pipeline Summary ===")
    for k, v in result.items():
        print(f"  {k:<16} {v}")
