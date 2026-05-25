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
        "id_field": "_reddit_author",
        "id_width": 20,
        "detail_field": "Archetype",
    },
    "m3_serpapi": {"detail_field": "City", "detail_width": 15},
    "m4_nonprofits": {"detail_field": "Archetype"},
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
) -> None:
    """Discover → score → print qualified leads (score >= 7)."""
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
    for lead in qualified:
        logger.info(
            "  %2s | %-*s | %-*s | %s",
            lead.get("Claude Score", "?"),
            id_width,
            lead.get(id_field, ""),
            detail_width,
            lead.get(detail_field, ""),
            lead["Source URL"][:url_width],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a discovery module standalone.")
    parser.add_argument("module", choices=list(_REGISTRY), help="Module to run")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run m3_serpapi with the full 288-call matrix instead of the default reduced matrix",
    )
    args = parser.parse_args()

    cfg = dict(_REGISTRY[args.module])
    mod = importlib.import_module(f"modules.{args.module}")

    # serpapi defaults to reduced=True (free tier); --full overrides to reduced=False
    if args.module == "m3_serpapi":
        discover_fn = (
            (lambda: mod.discover(reduced=False))
            if args.full
            else (lambda: mod.discover(reduced=True))
        )
    else:
        discover_fn = mod.discover

    run(discover_fn, **cfg)
