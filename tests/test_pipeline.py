"""Unit tests for pipeline.py — all external I/O mocked."""

from unittest.mock import MagicMock, patch

import pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_lead(url="https://example.com/1", source="youtube", archetype="health"):
    return {
        "Archetype": archetype,
        "Source": source,
        "Source URL": url,
        "Status": "New",
        "_content": "Story content.",
    }


def _scored_lead(url="https://example.com/1", score=8, disposition="auto"):
    lead = _raw_lead(url)
    lead["Claude Score"] = score
    lead["_disposition"] = disposition
    lead["_archetype_match"] = True
    return lead


# ---------------------------------------------------------------------------
# run() — stage-by-stage verification
# ---------------------------------------------------------------------------


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["apollo"], "discover", return_value=[])
@patch.object(pipeline.MODULES["nonprofits"], "discover", return_value=[])
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover")
def test_run_calls_all_modules(
    mock_yt,
    mock_rd,
    mock_sp,
    mock_np,
    mock_ap,
    mock_score,
    mock_enrich,
    mock_dispatch,
    mock_at,
):
    mock_yt.return_value = [_raw_lead()]
    mock_score.return_value = _scored_lead(score=8)
    mock_dispatch.return_value = {
        **_scored_lead(score=8),
        "_outreach_decision": "instantly",
    }
    mock_at.return_value.upsert = MagicMock()

    pipeline.run()

    mock_yt.assert_called_once()
    mock_rd.assert_called_once()
    mock_sp.assert_called_once()
    mock_np.assert_called_once()
    mock_ap.assert_called_once()


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["apollo"], "discover", return_value=[])
@patch.object(pipeline.MODULES["nonprofits"], "discover", return_value=[])
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover")
def test_run_filters_below_threshold(
    mock_yt,
    mock_rd,
    mock_sp,
    mock_np,
    mock_ap,
    mock_score,
    mock_enrich,
    mock_dispatch,
    mock_at,
):
    mock_yt.return_value = [_raw_lead("u1"), _raw_lead("u2")]
    # First lead scores above threshold, second below
    mock_score.side_effect = [
        _scored_lead("u1", score=8),
        _scored_lead("u2", score=4),
    ]
    mock_at.return_value.upsert = MagicMock()

    result = pipeline.run()

    assert result["qualifying"] == 1
    mock_enrich.assert_called_once()


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["apollo"], "discover", return_value=[])
@patch.object(pipeline.MODULES["nonprofits"], "discover", return_value=[])
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover")
def test_run_returns_summary(
    mock_yt,
    mock_rd,
    mock_sp,
    mock_np,
    mock_ap,
    mock_score,
    mock_enrich,
    mock_dispatch,
    mock_at,
):
    mock_yt.return_value = [_raw_lead("u1"), _raw_lead("u2")]
    qualifying = _scored_lead("u1", score=9)
    mock_score.side_effect = [qualifying, _scored_lead("u2", score=3)]
    qualifying["_outreach_decision"] = "instantly"
    mock_dispatch.side_effect = lambda lead, **kw: (
        lead.__setitem__("_outreach_decision", "instantly") or lead
    )
    mock_at.return_value.upsert = MagicMock()

    result = pipeline.run()

    assert result["discovered"] == 2
    assert result["qualifying"] == 1
    assert result["dispatched"] == 1
    assert result["review_queue"] == 0
    assert result["skipped"] == 0
    assert result["errors"] == 0


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["serpapi"], "discover")
@patch.object(pipeline.MODULES["youtube"], "discover")
def test_run_with_subset_of_modules(
    mock_yt,
    mock_sp,
    mock_score,
    mock_enrich,
    mock_dispatch,
    mock_at,
):
    mock_yt.return_value = [_raw_lead()]
    mock_sp.return_value = []
    mock_score.return_value = _scored_lead(score=3)
    mock_at.return_value.upsert = MagicMock()

    result = pipeline.run(module_names=["youtube", "serpapi"])

    mock_yt.assert_called_once()
    mock_sp.assert_called_once()
    assert result["discovered"] == 1


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["apollo"], "discover", return_value=[])
@patch.object(pipeline.MODULES["nonprofits"], "discover", return_value=[])
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover")
def test_run_upserts_qualifying_leads_to_airtable(
    mock_yt,
    mock_rd,
    mock_sp,
    mock_np,
    mock_ap,
    mock_score,
    mock_enrich,
    mock_dispatch,
    mock_at,
):
    mock_yt.return_value = [_raw_lead()]
    lead = _scored_lead(score=8)
    mock_score.return_value = lead
    mock_dispatch.side_effect = lambda lead, **kw: (
        lead.__setitem__("_outreach_decision", "instantly") or lead
    )
    mock_upsert = MagicMock()
    mock_at.return_value.upsert = mock_upsert

    pipeline.run()

    mock_upsert.assert_called_once()


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["apollo"], "discover", side_effect=Exception("API down"))
@patch.object(pipeline.MODULES["nonprofits"], "discover", return_value=[])
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover", return_value=[])
def test_run_discovery_error_continues(
    mock_yt,
    mock_rd,
    mock_sp,
    mock_np,
    mock_ap,
    mock_score,
    mock_enrich,
    mock_dispatch,
    mock_at,
):
    mock_at.return_value.upsert = MagicMock()
    # Should not raise even when a module fails
    result = pipeline.run()
    assert result["discovered"] == 0
