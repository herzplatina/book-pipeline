"""Master pipeline orchestrator.

Runs all discovery modules → scores with Claude → enriches via Hunter.io
→ dispatches via Hunter Sequences or human review queue → upserts to Airtable.

Usage:
    python pipeline.py                    # active default modules
    python pipeline.py --modules youtube reddit serpapi listennotes
"""

import argparse
import contextlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from config.settings import CLAUDE_SCORE_THRESHOLD
from crm.airtable import get_client
from crm.schema import build_queue_record
from enrichment.hunter import enrich
from modules import m1_youtube, m2_reddit, m3_serpapi, m4_listennotes, m5_apollo
from notifications.email_report import send_run_report
from outreach.hunter_sequences import dispatch, route
from scoring.claude_scorer import score

# Smoke-test matrix limits — one call per source, enough to exercise the full
# pipeline path without burning API quota.
_SMOKE_YOUTUBE_MAX_RESULTS = 5
_SMOKE_SERPAPI_MAX_CELLS = 3
_SMOKE_REDDIT_LIMIT = 5
_SMOKE_LISTENNOTES_QUERIES = 1

logger = logging.getLogger(__name__)

# Registry of all discovery modules by short name
MODULES: dict = {
    "youtube": m1_youtube,
    "reddit": m2_reddit,
    "serpapi": m3_serpapi,
    "listennotes": m4_listennotes,
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
        "podcast_name": lead.get("Podcast Name"),
        "episode_title": lead.get("Episode Title"),
        "website_urls": lead.get("Website URLs"),
        "interviewee_metadata": lead.get("Interviewee Metadata"),
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


@contextlib.contextmanager
def _apply_smoke_test_config():
    """Temporarily patch each module's globals to minimal smoke-test values.

    Modules import names from config.settings at module load time, so patching
    the settings module itself has no effect — we must update the references
    in each module's own namespace instead.

    Originals are saved and restored so repeated calls within the same process
    (e.g. tests) start from the same baseline.
    """
    _orig_yt_queries = m1_youtube.YOUTUBE_SEARCH_QUERIES
    _orig_yt_filters = m1_youtube.YOUTUBE_FILTERS
    _orig_rd_subreddits = m2_reddit.SUBREDDITS
    _orig_rd_keywords = m2_reddit.REDDIT_KEYWORDS
    _orig_rd_filters = m2_reddit.REDDIT_FILTERS
    _orig_ln_queries = m4_listennotes.LISTENNOTES_QUERIES
    _orig_sp_max_cells = m3_serpapi._smoke_max_cells

    try:
        # YouTube: 1 query per archetype, 5 results each
        m1_youtube.YOUTUBE_SEARCH_QUERIES = {
            archetype: queries[:1] for archetype, queries in _orig_yt_queries.items()
        }
        m1_youtube.YOUTUBE_FILTERS = {
            **_orig_yt_filters,
            "maxResults": _SMOKE_YOUTUBE_MAX_RESULTS,
        }

        # Reddit: 1 subreddit per archetype, 1 keyword, reduced limit
        m2_reddit.SUBREDDITS = {
            archetype: subs[:1] for archetype, subs in _orig_rd_subreddits.items()
        }
        m2_reddit.REDDIT_KEYWORDS = _orig_rd_keywords[:1]
        m2_reddit.REDDIT_FILTERS = {**_orig_rd_filters, "limit": _SMOKE_REDDIT_LIMIT}

        # ListenNotes: 1 query
        m4_listennotes.LISTENNOTES_QUERIES = _orig_ln_queries[
            :_SMOKE_LISTENNOTES_QUERIES
        ]

        # SerpApi: cap matrix cells
        m3_serpapi._smoke_max_cells = _SMOKE_SERPAPI_MAX_CELLS

        logger.info(
            "Smoke-test mode: YouTube maxResults=%d, Reddit limit=%d, "
            "ListenNotes queries=%d, SerpApi max_cells=%d",
            _SMOKE_YOUTUBE_MAX_RESULTS,
            _SMOKE_REDDIT_LIMIT,
            _SMOKE_LISTENNOTES_QUERIES,
            _SMOKE_SERPAPI_MAX_CELLS,
        )
        yield
    finally:
        m1_youtube.YOUTUBE_SEARCH_QUERIES = _orig_yt_queries
        m1_youtube.YOUTUBE_FILTERS = _orig_yt_filters
        m2_reddit.SUBREDDITS = _orig_rd_subreddits
        m2_reddit.REDDIT_KEYWORDS = _orig_rd_keywords
        m2_reddit.REDDIT_FILTERS = _orig_rd_filters
        m4_listennotes.LISTENNOTES_QUERIES = _orig_ln_queries
        m3_serpapi._smoke_max_cells = _orig_sp_max_cells


def run(
    module_names: list[str] | None = None,
    *,
    report_dir: str | Path | None = None,
    no_dispatch: bool = False,
    smoke_test: bool = False,
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
    smoke_ctx = _apply_smoke_test_config() if smoke_test else contextlib.nullcontext()
    with smoke_ctx:
        return _run_inner(
            module_names,
            report_dir=report_dir,
            no_dispatch=no_dispatch,
        )


def _run_inner(
    module_names: list[str] | None = None,
    *,
    report_dir: str | Path | None = None,
    no_dispatch: bool = False,
) -> dict:
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

    # --- Stage 4: Enrich + per-source stats init ---
    per_source: dict[str, dict] = {}
    for lead in qualifying:
        src = lead.get("Source", "unknown")
        stats = per_source.setdefault(
            src,
            {
                "qualifying": 0,
                "scores": [],
                "hunter_enriched": 0,
                "hunter_errors": {},
                "dispatched": 0,
                "contacts_upserted": 0,
                "dm_queue_written": 0,
            },
        )
        stats["qualifying"] += 1
        if s := lead.get("Claude Score"):
            stats["scores"].append(s)

        had_email = bool(lead.get("Email"))
        hunter_errors: list[dict] = []
        try:
            enrich(lead, _errors=hunter_errors)
            if not had_email and lead.get("Email"):
                stats["hunter_enriched"] += 1
        except Exception as exc:
            logger.exception(
                "Enrichment failed for url=%s", lead.get("Source URL", "?")
            )
            _record_error(errors, stage="enrich", exc=exc, lead=lead)
        for e in hunter_errors:
            key = f"{e['type']} {e.get('status', '')}"
            stats["hunter_errors"][key] = stats["hunter_errors"].get(key, 0) + 1

    # --- Stage 5: Dispatch + CRM routing ---
    # Routing rules:
    #   hunter_sequence → dispatch to Hunter Sequence + upsert to Contacts table
    #   review_queue    → add to Manual DM Queue only; never upsert to Contacts
    #   skip            → discard; no Airtable writes
    _decision_key = {"hunter_sequence": "dispatched", "skip": "skipped"}
    counts = {"dispatched": 0, "review_queue": 0, "skipped": 0}
    for lead in qualifying:
        src = lead.get("Source", "unknown")
        stats = per_source[src]
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
            # In no-dispatch mode, review_queue leads still need to reach the
            # Manual DM Queue — dispatch() is suppressed so we write directly.
            if lead["_outreach_decision"] == "review_queue":
                try:
                    airtable.add_to_manual_queue(build_queue_record(lead))
                    lead["_dm_queue_written"] = True
                except Exception as exc:
                    logger.exception(
                        "Manual queue write failed for url=%s",
                        lead.get("Source URL", "?"),
                    )
                    _record_error(errors, stage="manual_queue", exc=exc, lead=lead)

        decision = lead.get("_outreach_decision", "skip")
        raw_key = _decision_key.get(decision, decision)
        if raw_key in counts:
            counts[raw_key] += 1

        # Only automatable leads go into the Contacts table.
        # review_queue leads are written to the Manual DM Queue by dispatch()
        # (live mode) or the no-dispatch block above (smoke-test mode).
        if decision == "hunter_sequence":
            stats["dispatched"] += 1
            try:
                airtable.upsert(lead)
                stats["contacts_upserted"] += 1
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

        if lead.get("_dm_queue_written"):
            stats["dm_queue_written"] += 1

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
    send_run_report(run_id, summary, per_source)
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
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help=(
            "Minimal discovery: 1 query/source, 5 YouTube results, "
            f"{_SMOKE_SERPAPI_MAX_CELLS} SerpApi cells. Full pipeline path, "
            "reduced API quota."
        ),
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
        smoke_test=args.smoke_test,
    )
    print_summary(result)
