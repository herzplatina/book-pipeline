"""Unit tests for pipeline.py — all external I/O mocked."""

import json
from unittest.mock import MagicMock, patch

import pytest

import pipeline


@pytest.fixture(autouse=True)
def _no_email(monkeypatch):
    """Suppress send_run_report in all pipeline tests."""
    monkeypatch.setattr(pipeline, "send_run_report", lambda *a, **kw: None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_lead(url="https://example.com/1", source="youtube", archetype="health"):
    return {
        "Archetype": archetype,
        "Source": source,
        "Source URL": url,
        "Channel URL": "https://www.youtube.com/channel/channel_123"
        if source == "youtube"
        else "",
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
@patch.object(pipeline.MODULES["listennotes"], "discover", return_value=[])
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover")
def test_run_calls_default_active_modules(
    mock_yt,
    mock_rd,
    mock_sp,
    mock_np,
    mock_score,
    mock_enrich,
    mock_dispatch,
    mock_at,
):
    mock_yt.return_value = [_raw_lead()]
    mock_score.return_value = _scored_lead(score=8)
    mock_dispatch.return_value = {
        **_scored_lead(score=8),
        "_outreach_decision": "hunter_sequence",
    }
    mock_at.return_value.upsert = MagicMock()

    pipeline.run()

    mock_yt.assert_called_once()
    mock_rd.assert_called_once()
    mock_np.assert_called_once()
    mock_sp.assert_called_once()


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["apollo"], "discover", return_value=[])
@patch.object(pipeline.MODULES["listennotes"], "discover", return_value=[])
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
@patch.object(pipeline.MODULES["listennotes"], "discover", return_value=[])
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
    qualifying["_outreach_decision"] = "hunter_sequence"
    mock_dispatch.side_effect = lambda lead, **kw: (
        lead.__setitem__("_outreach_decision", "hunter_sequence") or lead
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
@patch.object(pipeline.MODULES["listennotes"], "discover", return_value=[])
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
        lead.__setitem__("_outreach_decision", "hunter_sequence") or lead
    )
    mock_upsert = MagicMock()
    mock_at.return_value.upsert = mock_upsert

    pipeline.run()

    mock_upsert.assert_called_once()


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["apollo"], "discover", return_value=[])
@patch.object(pipeline.MODULES["listennotes"], "discover", return_value=[])
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover")
def test_run_review_queue_leads_skip_contacts_upsert(
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
    """review_queue leads must never be written to the Contacts table."""
    mock_yt.return_value = [_raw_lead()]
    lead = _scored_lead(score=8)
    mock_score.return_value = lead
    mock_dispatch.side_effect = lambda lead, **kw: (
        lead.__setitem__("_outreach_decision", "review_queue") or lead
    )
    mock_upsert = MagicMock()
    mock_at.return_value.upsert = mock_upsert

    result = pipeline.run()

    mock_upsert.assert_not_called()
    assert result["review_queue"] == 1
    assert result["dispatched"] == 0


@patch("pipeline.get_client")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["listennotes"], "discover", return_value=[])
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover")
def test_run_no_dispatch_review_queue_writes_manual_queue(
    mock_yt, mock_rd, mock_sp, mock_np, mock_score, mock_enrich, mock_at
):
    """no_dispatch=True: review_queue leads must still reach the Manual DM Queue."""
    mock_yt.return_value = [_raw_lead()]
    lead = _scored_lead(score=7, disposition="review")
    mock_score.return_value = lead
    mock_add_queue = MagicMock()
    mock_upsert = MagicMock()
    mock_at.return_value.add_to_manual_queue = mock_add_queue
    mock_at.return_value.upsert = mock_upsert

    result = pipeline.run(no_dispatch=True)

    mock_add_queue.assert_called_once()
    mock_upsert.assert_not_called()
    assert result["review_queue"] == 1


@patch("pipeline.get_client")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["listennotes"], "discover", return_value=[])
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover")
def test_run_no_dispatch_hunter_sequence_upserts_contacts(
    mock_yt, mock_rd, mock_sp, mock_np, mock_score, mock_enrich, mock_at
):
    """no_dispatch=True: hunter_sequence leads are upserted to Contacts, no Hunter call."""
    mock_yt.return_value = [_raw_lead()]
    lead = _scored_lead(score=8, disposition="auto")
    lead["Email"] = "jane@example.com"
    mock_score.return_value = lead
    mock_upsert = MagicMock()
    mock_at.return_value.upsert = mock_upsert

    with patch("outreach.hunter_sequences.HUNTER_SEQUENCE_ID", "seq-123"):
        result = pipeline.run(no_dispatch=True)

    mock_upsert.assert_called_once()
    assert result["dispatched"] == 1


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["listennotes"], "discover", return_value=[])
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover", return_value=[])
def test_run_discovery_error_continues(
    mock_yt,
    mock_rd,
    mock_sp,
    mock_np,
    mock_score,
    mock_enrich,
    mock_dispatch,
    mock_at,
):
    mock_at.return_value.upsert = MagicMock()
    # Should not raise even when a module fails
    result = pipeline.run()
    assert result["discovered"] == 0


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["apollo"], "discover", return_value=[])
@patch.object(
    pipeline.MODULES["listennotes"], "discover", side_effect=Exception("API down")
)
@patch.object(pipeline.MODULES["serpapi"], "discover", return_value=[])
@patch.object(pipeline.MODULES["reddit"], "discover", return_value=[])
@patch.object(pipeline.MODULES["youtube"], "discover", return_value=[])
def test_run_writes_report_artifacts(
    mock_yt,
    mock_rd,
    mock_sp,
    mock_np,
    mock_ap,
    mock_score,
    mock_enrich,
    mock_dispatch,
    mock_at,
    tmp_path,
):
    mock_at.return_value.upsert = MagicMock()

    result = pipeline.run(report_dir=tmp_path)

    assert result["errors"] == 1
    summary_files = list(tmp_path.glob("*-summary.json"))
    error_files = list(tmp_path.glob("*-errors.log"))
    qualified_files = list(tmp_path.glob("*-qualified-leads.json"))
    assert len(summary_files) == 1
    assert len(error_files) == 1
    assert len(qualified_files) == 1

    payload = json.loads(summary_files[0].read_text(encoding="utf-8"))
    assert payload["summary"]["discovered"] == 0
    assert payload["errors"][0]["stage"] == "discover"
    assert payload["errors"][0]["module"] == "listennotes"
    assert "API down" in error_files[0].read_text(encoding="utf-8")
    assert json.loads(qualified_files[0].read_text(encoding="utf-8")) == []


@patch("pipeline.get_client")
@patch("pipeline.dispatch")
@patch("pipeline.enrich")
@patch("pipeline.score")
@patch.object(pipeline.MODULES["youtube"], "discover")
def test_run_checkpoints_qualified_youtube_channel_url(
    mock_yt,
    mock_score,
    mock_enrich,
    mock_dispatch,
    mock_at,
    tmp_path,
):
    high = _raw_lead("https://www.youtube.com/watch?v=high")
    low = _raw_lead("https://www.youtube.com/watch?v=low")
    high_scored = _scored_lead("https://www.youtube.com/watch?v=high", score=8)
    low_scored = _scored_lead("https://www.youtube.com/watch?v=low", score=4)
    high_scored["Channel URL"] = high["Channel URL"]
    low_scored["Channel URL"] = low["Channel URL"]
    mock_yt.return_value = [high, low]
    mock_score.side_effect = [high_scored, low_scored]
    mock_dispatch.side_effect = lambda lead, **kw: (
        lead.__setitem__("_outreach_decision", "hunter_sequence") or lead
    )
    mock_at.return_value.upsert = MagicMock()

    pipeline.run(module_names=["youtube"], report_dir=tmp_path)

    qualified_file = next(tmp_path.glob("*-qualified-leads.json"))
    qualified = json.loads(qualified_file.read_text(encoding="utf-8"))
    assert len(qualified) == 1
    assert qualified[0]["source_url"] == "https://www.youtube.com/watch?v=high"
    assert qualified[0]["channel_url"] == "https://www.youtube.com/channel/channel_123"
    upserted_lead = mock_at.return_value.upsert.call_args.args[0]
    assert upserted_lead["Channel URL"] == "https://www.youtube.com/channel/channel_123"
