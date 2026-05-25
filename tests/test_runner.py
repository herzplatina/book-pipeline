"""Unit tests for modules/runner.py."""

from unittest.mock import patch


def _make_lead(
    score, url="https://example.com/1", name="Jane Smith", archetype="health"
):
    return {
        "Claude Score": score,
        "Name": name,
        "Archetype": archetype,
        "Source URL": url,
    }


@patch("modules.runner.logging")
def test_run_prints_qualified_leads(mock_logging, capsys):
    from modules.runner import run

    leads = [_make_lead(8), _make_lead(5, url="https://example.com/2")]

    with patch("scoring.claude_scorer.score", side_effect=lambda lead: lead):
        run(lambda: leads)

    captured = capsys.readouterr().out
    assert "Found 1 qualified leads (score >= 7) from 2 raw" in captured
    assert "Jane Smith" in captured


@patch("modules.runner.logging")
def test_run_prints_nothing_when_no_qualified(mock_logging, capsys):
    from modules.runner import run

    leads = [_make_lead(3), _make_lead(6)]
    with patch("scoring.claude_scorer.score", side_effect=lambda lead: lead):
        run(lambda: leads)

    captured = capsys.readouterr().out
    assert "Found 0 qualified leads (score >= 7) from 2 raw" in captured


@patch("modules.runner.logging")
def test_run_uses_custom_id_and_detail_fields(mock_logging, capsys):
    from modules.runner import run

    lead = {
        "Claude Score": 9,
        "_reddit_author": "u/johndoe",
        "Archetype": "criminal",
        "Source URL": "https://reddit.com/r/foo/1",
    }
    with patch("scoring.claude_scorer.score", side_effect=lambda lead: lead):
        run(lambda: [lead], id_field="_reddit_author", id_width=20)

    captured = capsys.readouterr().out
    assert "u/johndoe" in captured


@patch("modules.runner.logging")
def test_run_handles_empty_discover(mock_logging, capsys):
    from modules.runner import run

    with patch("scoring.claude_scorer.score", side_effect=lambda lead: lead):
        run(lambda: [])

    captured = capsys.readouterr().out
    assert "Found 0 qualified leads (score >= 7) from 0 raw" in captured
