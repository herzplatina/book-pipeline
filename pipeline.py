"""Master pipeline orchestrator.

Runs all discovery modules → scores with Claude → enriches via Hunter.io
→ dispatches via Hunter Sequences or human review queue → upserts to Airtable.

Usage:
    python pipeline.py                    # active default modules
    python pipeline.py --modules youtube reddit serpapi listennotes
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from config.settings import CLAUDE_SCORE_THRESHOLD
from crm.airtable import get_client
from enrichment.hunter import enrich
from modules import m1_youtube, m2_reddit, m3_serpapi, m4_nonprofits, m5_apollo
from outreach.hunter_sequences import dispatch, route
from scoring.claude_scorer import score

logger = logging.getLogger(__name__)

# Registry of all discovery modules by short name
MODULES: dict = {
    "youtube": m1_youtube,
    "reddit": m2_reddit,
    "serpapi": m3_serpapi,
    "listennotes": m4_nonprofits,
    "apollo": m5_apollo,
}

# Active lead sources for the current operating phase.
# Apollo remains available through --modules for later/manual runs.
DEFAULT_MODULES = ["youtube", "reddit", "serpapi", "listennotes"]


def _record_error(
    errors: list[dict],
    *,
    stage: str,
    exc: Exception,
    module: str | None = None,
    lead: dict | None = None,
) -> None:
    """Append non-secret failure context for run reports."""
    errors.append(
        {
            "stage": stage,
            "module": module,
            "source": lead.get("Source") if lead else None,
            "source_url": lead.get("Source URL") if lead else None,
            "archetype": lead.get("Archetype") if lead else None,
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    )


def _write_run_report(
    summary: dict,
    errors: list[dict],
    qualifying_leads: list[dict],
    *,
    report_dir: str | Path,
    run_id: str,
) -> None:
    """Write GitHub Actions-friendly run artifacts under report_dir."""
    path = Path(report_dir)
    path.mkdir(parents=True, exist_ok=True)

    payload = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "errors": errors,
    }
    summary_path = path / f"{run_id}-summary.json"
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    errors_path = path / f"{run_id}-errors.log"
    if errors:
        lines = [
            (
                f"{item['stage']} module={item.get('module') or '-'} "
                f"source={item.get('source') or '-'} "
                f"archetype={item.get('archetype') or '-'} "
                f"url={item.get('source_url') or '-'} "
                f"{item['exception_type']}: {item['message']}"
            )
            for item in errors
        ]
        errors_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        errors_path.write_text("No errors recorded.\n", encoding="utf-8")

    qualified_path = path / f"{run_id}-qualified-leads.json"
    qualified_payload = [_checkpoint_lead(lead) for lead in qualifying_leads]
    qualified_path.write_text(
        json.dumps(qualified_payload, indent=2) + "\n", encoding="utf-8"
    )

    logger.info("Wrote run report artifacts to %s", path)


def _checkpoint_lead(lead: dict) -> dict:
    """Return non-secret qualified lead fields useful for post-run review."""
    return {
        "name": lead.get("Name"),
        "source": lead.get("Source"),
        "source_url": lead.get("Source URL"),
        "channel_url": lead.get("Channel URL"),
        "archetype": lead.get("Archetype"),
        "claude_score": lead.get("Claude Score"),
        "archetype_match": lead.get("_archetype_match"),
        "disposition": lead.get("_disposition"),
        "story_summary": lead.get("Story Summary"),
        "turning_point": lead.get("Turning Point"),
        "contact_method": lead.get("Contact Method"),
        "contact_value": lead.get("Contact Value"),
        "email": lead.get("Email"),
    }


def print_summary(summary: dict) -> None:
    """Print the compact final summary intended for humans in CI logs."""
    print("\n=== Pipeline Summary ===")
    for k, v in summary.items():
        print(f"  {k:<16} {v}")


def run(
    module_names: list[str] | None = None,
    *,
    report_dir: str | Path | None = None,
    no_dispatch: bool = False,
) -> dict:
    """Run the pipeline end-to-end. Returns a summary dict.

    Args:
        module_names: List of module keys from MODULES to run.
                      Defaults to DEFAULT_MODULES when None.
        no_dispatch:  If True, skip outreach dispatch but still enrich.
                      Contacts upsert still only runs for hunter_sequence leads.
                      Useful for dry-run testing.

    Returns:
        Summary with keys: discovered, qualifying, dispatched,
        review_queue, skipped, errors.
    """
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names = module_names or DEFAULT_MODULES
    airtable = get_client()
    errors: list[dict] = []

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
            logger.exception("Discovery failed for module=%s", name)
            _record_error(errors, stage="discover", module=name, exc=exc)

    logger.info("Total raw leads: %d", len(all_raw))

    # --- Stage 2: Score ---
    scored: list[dict] = []
    for lead in all_raw:
        try:
            scored.append(score(lead))
        except Exception as exc:
            logger.exception("Scoring failed for url=%s", lead.get("Source URL", "?"))
            _record_error(errors, stage="score", exc=exc, lead=lead)

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
    for lead in qualifying:
        if lead.get("Source") == "youtube" and lead.get("Channel URL"):
            logger.info(
                "Qualified YouTube lead channel_url=%s source_url=%s score=%s",
                lead["Channel URL"],
                lead.get("Source URL", ""),
                lead.get("Claude Score", ""),
            )

    # --- Stage 4: Enrich ---
    for lead in qualifying:
        try:
            enrich(lead)
        except Exception as exc:
            logger.exception(
                "Enrichment failed for url=%s", lead.get("Source URL", "?")
            )
            _record_error(errors, stage="enrich", exc=exc, lead=lead)

    # --- Stage 5: Dispatch + CRM routing ---
    # Routing rules:
    #   hunter_sequence → dispatch to Hunter Sequence + upsert to Contacts table
    #   review_queue    → add to Manual DM Queue only; never upsert to Contacts
    #   skip            → discard; no Airtable writes
    _decision_key = {"hunter_sequence": "dispatched", "skip": "skipped"}
    counts = {"dispatched": 0, "review_queue": 0, "skipped": 0}
    for lead in qualifying:
        # Determine routing — dispatch() sets _outreach_decision as a side-effect,
        # so call route() first when dispatch is suppressed (--no-dispatch testing).
        if not no_dispatch:
            try:
                dispatch(lead, airtable_client=airtable)
            except Exception as exc:
                logger.exception(
                    "Dispatch failed for url=%s", lead.get("Source URL", "?")
                )
                _record_error(errors, stage="dispatch", exc=exc, lead=lead)
        else:
            lead["_outreach_decision"] = route(lead)

        decision = lead.get("_outreach_decision", "skip")
        raw_key = _decision_key.get(decision, decision)
        if raw_key in counts:
            counts[raw_key] += 1

        # Only automatable leads go into the Contacts table.
        # review_queue leads are already written to the Manual DM Queue by dispatch().
        if decision == "hunter_sequence":
            try:
                airtable.upsert(lead)
            except Exception as exc:
                logger.exception(
                    "Airtable upsert failed for url=%s", lead.get("Source URL", "?")
                )
                _record_error(errors, stage="airtable_upsert", exc=exc, lead=lead)
        else:
            logger.info(
                "Contacts upsert skipped (decision=%s) for url=%s",
                decision,
                lead.get("Source URL", ""),
            )

    summary = {
        "discovered": len(all_raw),
        "scored": len(scored),
        "qualifying": len(qualifying),
        **counts,
        "errors": len(errors),
    }
    logger.info("Pipeline complete: %s", summary)
    if report_dir:
        _write_run_report(
            summary,
            errors,
            qualifying,
            report_dir=report_dir,
            run_id=run_id,
        )
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the book-pipeline.")
    parser.add_argument(
        "--modules",
        nargs="+",
        choices=list(MODULES.keys()),
        metavar="MODULE",
        help=f"Modules to run (default: {' '.join(DEFAULT_MODULES)}).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    parser.add_argument(
        "--report-dir",
        default="data/runs",
        help="Directory for JSON/error-log run artifacts (default: data/runs).",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Do not write run report artifacts.",
    )
    parser.add_argument(
        "--no-dispatch",
        action="store_true",
        help="Skip outreach dispatch; still enriches and upserts to Airtable.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    result = run(
        args.modules,
        report_dir=None if args.no_report else args.report_dir,
        no_dispatch=args.no_dispatch,
    )
    print_summary(result)
