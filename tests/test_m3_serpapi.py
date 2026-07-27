"""Unit tests for modules/m3_serpapi.py — all external I/O is mocked."""

from unittest.mock import patch

import modules.m3_serpapi as m3

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_serpapi_result(url="https://detroitnews.com/story/123"):
    return {
        "link": url,
        "title": "Detroit woman builds bakery after pandemic layoff",
        "snippet": "Jane Smith lost her job...",
        "source": "Detroit News",
    }


# ---------------------------------------------------------------------------
# _build_matrix
# ---------------------------------------------------------------------------


def test_build_matrix_reduced():
    m3.REDUCED_MATRIX = True
    matrix = m3._build_matrix()
    # 5 cities × 6 windows × 3 queries
    assert len(matrix) == 5 * 6 * 3


def test_build_matrix_full():
    m3.REDUCED_MATRIX = False
    matrix = m3._build_matrix()
    # 8 cities × 6 windows × 6 queries
    assert len(matrix) == 8 * 6 * 6
    m3.REDUCED_MATRIX = True  # reset


# ---------------------------------------------------------------------------
# _build_lead
# ---------------------------------------------------------------------------


def test_build_lead_sets_required_fields():
    result = _make_serpapi_result()
    lead = m3._build_lead(
        result, "Full article text.", ["Reporter"], "Detroit", "rebuild_peak"
    )

    assert lead["Archetype"] == "bluecollar"
    assert lead["Source"] == "serpapi"
    assert lead["Source URL"] == result["link"]
    assert lead["City"] == "Detroit"
    assert lead["Date Window"] == "rebuild_peak"
    assert lead["Status"] == "New"


def test_build_lead_stores_content_for_scorer():
    result = _make_serpapi_result()
    lead = m3._build_lead(result, "Full article text.", [], "Detroit", "rebuild_peak")
    assert lead["_content"] == "Full article text."


def test_build_lead_stores_authors():
    result = _make_serpapi_result()
    lead = m3._build_lead(result, "text", ["Alice Reporter"], "Detroit", "late_covid")
    assert lead["_authors"] == ["Alice Reporter"]


def test_build_lead_has_no_scoring_fields():
    """Scoring fields must be absent — scorer adds them later."""
    result = _make_serpapi_result()
    lead = m3._build_lead(result, "text", [], "Detroit", "rebuild_peak")
    assert "Claude Score" not in lead
    assert "Story Summary" not in lead
    assert "Name" not in lead


# ---------------------------------------------------------------------------
# discover() — all external I/O mocked
# ---------------------------------------------------------------------------


@patch("modules.m3_serpapi.time.sleep")
@patch("modules.m3_serpapi._fetch_article")
@patch("modules.m3_serpapi._serpapi_search")
def test_discover_returns_raw_leads(mock_serp, mock_fetch, mock_sleep):
    m3.REDUCED_MATRIX = True
    mock_serp.return_value = [_make_serpapi_result("https://detroitnews.com/story/1")]
    mock_fetch.return_value = (
        "Long article text about Jane building a bakery.",
        ["Reporter"],
    )

    leads = m3.discover(reduced=True)

    assert len(leads) >= 1
    assert leads[0]["Archetype"] == "bluecollar"
    assert leads[0]["Source"] == "serpapi"
    assert "_content" in leads[0]
    # No scoring fields — discover no longer scores
    assert "Claude Score" not in leads[0]


@patch("modules.m3_serpapi.time.sleep")
@patch("modules.m3_serpapi._fetch_article")
@patch("modules.m3_serpapi._serpapi_search")
def test_discover_deduplicates_urls(mock_serp, mock_fetch, mock_sleep):
    m3.REDUCED_MATRIX = True
    same_url = "https://detroitnews.com/story/dupe"
    mock_serp.return_value = [_make_serpapi_result(same_url)]
    mock_fetch.return_value = ("Article text.", [])

    leads = m3.discover(reduced=True)

    # URL appears in multiple matrix cells — must only be processed once
    urls = [lead["Source URL"] for lead in leads]
    assert urls.count(same_url) == 1


@patch("modules.m3_serpapi.time.sleep")
@patch("modules.m3_serpapi._fetch_article")
@patch("modules.m3_serpapi._serpapi_search")
def test_discover_skips_empty_articles(mock_serp, mock_fetch, mock_sleep):
    m3.REDUCED_MATRIX = True
    mock_serp.return_value = [_make_serpapi_result()]
    mock_fetch.return_value = ("", [])  # download failed

    leads = m3.discover(reduced=True)
    assert leads == []


@patch("modules.m3_serpapi.time.sleep")
@patch("modules.m3_serpapi._serpapi_search")
def test_discover_serpapi_error_continues(mock_serp, mock_sleep):
    m3.REDUCED_MATRIX = True
    import requests as req_lib

    mock_serp.side_effect = req_lib.HTTPError("429 Too Many Requests")

    # Should not raise — errors are caught and logged
    leads = m3.discover(reduced=True)
    assert leads == []


@patch("modules.m3_serpapi.time.sleep")
@patch("modules.m3_serpapi._fetch_article")
@patch("modules.m3_serpapi._serpapi_search")
def test_discover_sleeps_between_calls(mock_serp, mock_fetch, mock_sleep):
    m3.REDUCED_MATRIX = True
    mock_serp.return_value = []
    mock_fetch.return_value = ("", [])

    m3.discover(reduced=True)

    # One sleep per matrix cell (5 cities × 6 windows × 3 queries = 90)
    assert mock_sleep.call_count == 90


@patch("modules.m3_serpapi.time.sleep")
@patch("modules.m3_serpapi._fetch_article")
@patch("modules.m3_serpapi._serpapi_search")
def test_discover_limits_matrix_cells(mock_serp, mock_fetch, mock_sleep):
    m3.REDUCED_MATRIX = True
    mock_serp.return_value = []
    mock_fetch.return_value = ("", [])

    m3.discover(reduced=True, max_cells=10)

    assert mock_serp.call_count == 10
    assert mock_sleep.call_count == 10
