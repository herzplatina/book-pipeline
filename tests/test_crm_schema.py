"""Tests for crm/schema.py — build_queue_record adapter and QUEUE_SOURCE_FIELDS."""

from crm.schema import QUEUE_SOURCE_FIELDS, build_queue_record


def _lead(**kwargs):
    base = {
        "Source": "youtube",
        "Source URL": "https://www.youtube.com/watch?v=abc",
        "Archetype": "health",
        "Status": "New",
        "Name": "Jane Smith",
        "Contact Method": "email",
        "Contact Value": "jane@example.com",
        "Story Summary": "Jane overcame cancer.",
    }
    base.update(kwargs)
    return base


_BASE_KEYS = {
    "Source URL",
    "Archetype",
    "Name",
    "Contact Method",
    "Contact Value",
    "Status",
    "Notes",
}


def test_build_queue_record_base_fields_always_present():
    record = build_queue_record(_lead())
    assert _BASE_KEYS.issubset(record.keys())
    assert record["Status"] == "Pending"
    assert record["Notes"] == "Jane overcame cancer."


def test_build_queue_record_unknown_source_produces_base_fields_only():
    record = build_queue_record(_lead(Source="future_source"))
    assert set(record.keys()) == _BASE_KEYS


# --- youtube ---


def test_build_queue_record_youtube_includes_channel_url():
    record = build_queue_record(_lead(**{"Channel URL": "https://youtube.com/c/jane"}))
    assert record["Channel URL"] == "https://youtube.com/c/jane"


def test_build_queue_record_youtube_omits_channel_url_when_absent():
    record = build_queue_record(_lead())  # no Channel URL
    assert "Channel URL" not in record


def test_build_queue_record_youtube_gets_no_reddit_or_podcast_fields():
    record = build_queue_record(_lead())
    for field in ("Reddit Username", "Subreddit", "Podcast Name", "Episode Title"):
        assert field not in record


# --- reddit ---


def test_build_queue_record_reddit_includes_username_and_subreddit():
    record = build_queue_record(
        _lead(
            Source="reddit",
            **{"Reddit Username": "u/johndoe", "Subreddit": "UberDrivers"},
        )
    )
    assert record["Reddit Username"] == "u/johndoe"
    assert record["Subreddit"] == "UberDrivers"


def test_build_queue_record_reddit_omits_empty_username():
    record = build_queue_record(_lead(Source="reddit"))  # no Reddit fields
    assert "Reddit Username" not in record
    assert "Subreddit" not in record


# --- listennotes ---


def test_build_queue_record_listennotes_includes_all_podcast_fields():
    record = build_queue_record(
        _lead(
            Source="listennotes",
            **{
                "Podcast Name": "Healing Show",
                "Episode Title": "Ep 1 — Jane Smith",
                "Website URLs": "https://janesmith.com",
                "Interviewee Metadata": '{"role":"coach"}',
            },
        )
    )
    assert record["Podcast Name"] == "Healing Show"
    assert record["Episode Title"] == "Ep 1 — Jane Smith"
    assert record["Website URLs"] == "https://janesmith.com"
    assert record["Interviewee Metadata"] == '{"role":"coach"}'


def test_build_queue_record_listennotes_omits_empty_podcast_fields():
    record = build_queue_record(_lead(Source="listennotes"))  # no podcast data
    assert "Podcast Name" not in record
    assert "Episode Title" not in record
    assert "Website URLs" not in record
    assert "Interviewee Metadata" not in record


def test_build_queue_record_listennotes_partial_fields_only_present_ones():
    record = build_queue_record(
        _lead(Source="listennotes", **{"Podcast Name": "Healing Show"})
    )
    assert record["Podcast Name"] == "Healing Show"
    assert "Episode Title" not in record


# --- serpapi ---


def test_build_queue_record_serpapi_includes_city_and_date_window():
    record = build_queue_record(
        _lead(Source="serpapi", City="Detroit", **{"Date Window": "2020-2021"})
    )
    assert record["City"] == "Detroit"
    assert record["Date Window"] == "2020-2021"


def test_build_queue_record_serpapi_omits_empty_city():
    record = build_queue_record(_lead(Source="serpapi"))
    assert "City" not in record
    assert "Date Window" not in record


# --- QUEUE_SOURCE_FIELDS registry ---


def test_all_known_sources_are_registered():
    assert set(QUEUE_SOURCE_FIELDS.keys()) == {
        "youtube",
        "reddit",
        "listennotes",
        "serpapi",
    }
