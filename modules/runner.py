"""Shared discovery runner.

As a helper (called from each module's __main__):
    from modules.runner import run
    run(discover)
    run(lambda: discover(reduced=True), detail_field="City")

As a CLI:
    python -m modules.runner m1_youtube
    python -m modules.runner m3_serpapi          # reduced matrix (default)
    python -m modules.runner m3_serpapi --full   # full matrix (288 SerpApi calls)
"""

import argparse
import importlib
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, dict] = {
    "m1_youtube": {"detail_field": "Archetype"},
    "m2_reddit": {
        "id_field": "Reddit Username",
        "id_width": 20,
        "detail_field": "Archetype",
    },
    "m3_serpapi": {"detail_field": "City", "detail_width": 15},
    "listennotes": {"import_name": "m4_listennotes", "detail_field": "Archetype"},
    "m4_listennotes": {"detail_field": "Archetype"},
    "m5_apollo": {"detail_field": "Email", "detail_width": 35, "url_width": 50},
}


def run(
    discover_fn: Callable,
    *,
    id_field: str = "Name",
    detail_field: str = "Archetype",
    id_width: int = 30,
    detail_width: int = 12,
    url_width: int = 60,
    show_all_scores: bool = False,
) -> None:
    """Discover → score → log qualified leads, optionally all scored leads."""
    from scoring import claude_scorer

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    raw = discover_fn()
    scored = [claude_scorer.score(lead) for lead in raw]
    qualified = [lead for lead in scored if (lead.get("Claude Score") or 0) >= 7]
    logger.info(
        "Found %d qualified leads (score >= 7) from %d raw", len(qualified), len(raw)
    )
    leads_to_show = scored if show_all_scores else qualified
    if show_all_scores:
        logger.info("All scored leads:")
    for lead in leads_to_show:
        logger.info(
            "  %2s | %-8s | match=%-5s | %-*s | %-*s | %s",
            lead.get("Claude Score", "?"),
            lead.get("_disposition", "?"),
            lead.get("_archetype_match", "?"),
            id_width,
            lead.get(id_field, ""),
            detail_width,
            lead.get(detail_field, ""),
            lead["Source URL"][:url_width],
        )
        if show_all_scores:
            logger.info("       summary: %s", lead.get("Story Summary") or "")
            logger.info("       turning_point: %s", lead.get("Turning Point") or "")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a discovery module standalone.")
    parser.add_argument("module", choices=list(_REGISTRY), help="Module to run")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run m3_serpapi with the full 288-call matrix instead of the default reduced matrix",
    )
    parser.add_argument(
        "--show-all-scores",
        action="store_true",
        help="Log every scored lead, not only leads scoring >= 7.",
    )
    args = parser.parse_args()

    cfg = dict(_REGISTRY[args.module])
    import_name = cfg.pop("import_name", args.module)
    mod = importlib.import_module(f"modules.{import_name}")

    # serpapi defaults to reduced=True (free tier); --full overrides to reduced=False
    if import_name == "m3_serpapi":
        discover_fn = (
            (lambda: mod.discover(reduced=False))
            if args.full
            else (lambda: mod.discover(reduced=True))
        )
    else:
        discover_fn = mod.discover

    run(discover_fn, show_all_scores=args.show_all_scores, **cfg)
