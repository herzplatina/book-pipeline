"""Unit tests for scoring/claude_scorer.py and scoring/prompts.py."""

import json
from unittest.mock import MagicMock, patch

import pytest

from scoring.prompts import ARCHETYPE_HINTS, build_user_message
from scoring import claude_scorer
from scoring.claude_scorer import ClaudeScorer, _parse_json_object, get_disposition


# ---------------------------------------------------------------------------
# prompts.py
# ---------------------------------------------------------------------------


def test_build_user_message_with_hint():
    msg = build_user_message("some text", archetype_hint="bluecollar hint")
    assert msg.startswith("Archetype hint: bluecollar hint")
    assert "Content:\nsome text" in msg


def test_build_user_message_no_hint():
    msg = build_user_message("some text")
    assert msg.startswith("Content:\nsome text")
    assert "Archetype hint" not in msg


def test_build_user_message_truncates_at_4000():
    long_text = "x" * 10_000
    msg = build_user_message(long_text)
    content_part = msg.split("Content:\n", 1)[1]
    assert len(content_part) == 4000


def test_archetype_hints_cover_all_archetypes():
    from crm.schema import ARCHETYPES

    for archetype in ARCHETYPES:
        if archetype == "other":
            continue  # 'other' intentionally has no hint
        assert archetype in ARCHETYPE_HINTS, f"Missing hint for archetype: {archetype}"


# ---------------------------------------------------------------------------
# get_disposition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score, archetype_match, expected",
    [
        (10, True, "auto"),
        (8, True, "auto"),
        (8, False, "review"),  # high score but wrong archetype → human gate
        (7, True, "review"),
        (6, True, "review"),
        (6, False, "review"),
        (5, True, "discard"),
        (1, False, "discard"),
    ],
)
def test_get_disposition(score, archetype_match, expected):
    assert get_disposition(score, archetype_match) == expected


# ---------------------------------------------------------------------------
# ClaudeScorer.score_text
# ---------------------------------------------------------------------------


def _mock_scorer(scoring_dict: dict) -> ClaudeScorer:
    scorer = ClaudeScorer.__new__(ClaudeScorer)
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text=json.dumps(scoring_dict))]
    fake_client.messages.create.return_value = fake_response
    scorer._client = fake_client
    return scorer


def _sample_scoring(**overrides) -> dict:
    base = {
        "score": 8,
        "name": "Jane Smith",
        "archetype": "bluecollar",
        "archetype_match": True,
        "turning_point": "She launched a bakery the week she was laid off.",
        "summary": "Jane pivoted from factory work to bakery ownership during Covid.",
        "contact_clue": "janesbakery.com",
    }
    return {**base, **overrides}


def test_score_text_returns_parsed_json():
    scorer = _mock_scorer(_sample_scoring())
    result = scorer.score_text("Some article about Jane building a bakery.")
    assert result["score"] == 8
    assert result["name"] == "Jane Smith"
    assert result["archetype_match"] is True


def test_parse_json_object_tolerates_markdown_wrapper():
    wrapped = '```json\n{"score": 8, "name": "Jane Smith"}\n```'
    result = _parse_json_object(wrapped)
    assert result["score"] == 8
    assert result["name"] == "Jane Smith"


def test_score_text_empty_returns_none():
    scorer = ClaudeScorer.__new__(ClaudeScorer)
    scorer._client = MagicMock()
    assert scorer.score_text("   ") is None
    scorer._client.messages.create.assert_not_called()


def test_score_text_bad_json_returns_none():
    scorer = ClaudeScorer.__new__(ClaudeScorer)
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="not json")]
    fake_client.messages.create.return_value = fake_response
    scorer._client = fake_client
    assert scorer.score_text("some text") is None


def test_score_text_passes_archetype_hint():
    scorer = _mock_scorer(_sample_scoring())
    scorer.score_text("text", archetype_hint="bluecollar hint")
    call_kwargs = scorer._client.messages.create.call_args.kwargs
    user_content = call_kwargs["messages"][0]["content"]
    assert "Archetype hint: bluecollar hint" in user_content


def test_score_text_prefills_assistant_json_object():
    scorer = _mock_scorer(_sample_scoring())
    scorer.score_text("text")
    call_kwargs = scorer._client.messages.create.call_args.kwargs
    assert call_kwargs["messages"][1] == {"role": "assistant", "content": "{"}


def test_score_text_readds_prefill_before_parsing():
    scorer = ClaudeScorer.__new__(ClaudeScorer)
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.content = [
        MagicMock(
            text=(
                '"score": 8, "name": "Jane Smith", "archetype": "bluecollar", '
                '"archetype_match": true, "turning_point": "She started.", '
                '"summary": "Jane rebuilt her career.", '
                '"contact_clue": null}'
            )
        )
    ]
    fake_client.messages.create.return_value = fake_response
    scorer._client = fake_client

    result = scorer.score_text("text")

    assert result["score"] == 8
    assert result["contact_clue"] is None


def test_score_text_uses_haiku_model():
    scorer = _mock_scorer(_sample_scoring())
    scorer.score_text("text")
    call_kwargs = scorer._client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# ClaudeScorer.score_lead
# ---------------------------------------------------------------------------


def test_score_lead_enriches_lead():
    scorer = _mock_scorer(
        _sample_scoring(score=8, name="Jane Smith", archetype_match=True)
    )
    lead = {
        "Archetype": "bluecollar",
        "Source": "serpapi",
        "Source URL": "https://example.com",
        "_content": "Article text.",
    }
    result = scorer.score_lead(lead)

    assert result["Claude Score"] == 8
    assert result["Story Summary"] is not None
    assert result["Turning Point"] is not None
    assert result["Name"] == "Jane Smith"
    assert result["First Name"] == "Jane"
    assert result["Last Name"] == "Smith"
    assert result["_archetype_match"] is True
    assert result["_disposition"] == "auto"
    assert result["_contact_clue"] == "janesbakery.com"


def test_score_lead_discard_on_low_score():
    scorer = _mock_scorer(_sample_scoring(score=3, archetype_match=False))
    lead = {"Archetype": "bluecollar", "_content": "Weak article."}
    result = scorer.score_lead(lead)
    assert result["_disposition"] == "discard"


def test_score_lead_review_on_archetype_mismatch():
    scorer = _mock_scorer(_sample_scoring(score=9, archetype_match=False))
    lead = {"Archetype": "bluecollar", "_content": "Good story wrong archetype."}
    result = scorer.score_lead(lead)
    assert result["_disposition"] == "review"


def test_score_lead_no_content_discards():
    scorer = _mock_scorer(_sample_scoring())
    lead = {"Archetype": "bluecollar", "_content": ""}
    result = scorer.score_lead(lead)
    assert result["_disposition"] == "discard"


def test_score_lead_does_not_overwrite_existing_name():
    scorer = _mock_scorer(_sample_scoring(name="Claude Name"))
    lead = {
        "Archetype": "bluecollar",
        "_content": "text",
        "Name": "Original Name",
        "First Name": "Original",
        "Last Name": "Name",
    }
    scorer.score_lead(lead)
    assert lead["Name"] == "Original Name"
    assert lead["First Name"] == "Original"


def test_score_lead_preserves_existing_contact_clue_when_claude_omits_it():
    scorer = _mock_scorer(_sample_scoring(contact_clue=None))
    lead = {
        "Archetype": "health",
        "_content": "Video description with jane@example.com.",
        "_contact_clue": "jane@example.com",
    }

    scorer.score_lead(lead)

    assert lead["_contact_clue"] == "jane@example.com"


def test_score_lead_uses_archetype_hint():
    scorer = _mock_scorer(_sample_scoring())
    lead = {"Archetype": "criminal", "_content": "story text"}
    scorer.score_lead(lead)
    call_kwargs = scorer._client.messages.create.call_args.kwargs
    user_content = call_kwargs["messages"][0]["content"]
    assert "incarcerated" in user_content  # from ARCHETYPE_HINTS['criminal']


# ---------------------------------------------------------------------------
# Module-level score() singleton
# ---------------------------------------------------------------------------


def test_module_score_function():
    scorer = _mock_scorer(_sample_scoring(score=9))
    with patch("scoring.claude_scorer._get_scorer", return_value=scorer):
        lead = {"Archetype": "bluecollar", "_content": "text"}
        result = claude_scorer.score(lead)
    assert result["Claude Score"] == 9


def test_singleton_is_reused():
    # Reset module singleton so we start fresh
    claude_scorer._scorer = None
    with patch("scoring.claude_scorer.ClaudeScorer") as MockClass:
        MockClass.return_value = _mock_scorer(_sample_scoring())
        claude_scorer._get_scorer()
        claude_scorer._get_scorer()
    # ClaudeScorer should only be instantiated once
    assert MockClass.call_count == 1
    claude_scorer._scorer = None  # clean up
