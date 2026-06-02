"""Unit tests for crm.airtable helpers."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from crm.airtable import (
    AirtableClient,
    _raise_for_status,
    _smoke_test_contact,
    _smoke_test_manual_queue_fields,
    run_smoke_test,
)
from crm.schema import validate_lead


def test_smoke_test_contact_is_valid_lead():
    lead = _smoke_test_contact("run123")

    assert validate_lead(lead) == []
    assert lead["Source"] == "serpapi"
    assert lead["Source URL"].endswith("/run123")
    assert "Synthetic" in lead["Story Summary"]


def test_smoke_test_manual_queue_fields():
    fields = _smoke_test_manual_queue_fields("run123")

    assert fields["Status"] == "Pending"
    assert fields["Channel"] == "Manual Email"
    assert fields["Source URL"].endswith("/run123")
    assert "Synthetic" in fields["Notes"]


@patch("crm.airtable.get_client")
def test_run_smoke_test_writes_and_reads_records(mock_get_client):
    client = MagicMock()
    client.upsert.return_value = {"id": "rec_contacts"}
    client.find_by_source_url.return_value = {"id": "rec_contacts"}
    client.add_to_manual_queue.return_value = {"id": "rec_queue"}
    client.list_manual_queue.return_value = [{"id": "rec_queue", "fields": {}}]
    mock_get_client.return_value = client

    result = run_smoke_test()

    assert result["contacts_record_id"] == "rec_contacts"
    assert result["contacts_readback_id"] == "rec_contacts"
    assert result["manual_queue_record_id"] == "rec_queue"
    assert result["manual_queue_readback_id"] == "rec_queue"
    client.upsert.assert_called_once()
    client.find_by_source_url.assert_called_once()
    client.add_to_manual_queue.assert_called_once()
    client.list_manual_queue.assert_called_once()
    mock_get_client.assert_called_once_with(error_body_limit=1000)


@patch.object(AirtableClient, "find_by_source_url", return_value=None)
@patch("crm.airtable.requests.post")
def test_upsert_defaults_created_at_to_date(mock_post, mock_find):
    client = AirtableClient("pat", "base")
    mock_post.return_value.json.return_value = {"id": "rec123"}

    client.upsert(
        {
            "Archetype": "bluecollar",
            "Source": "serpapi",
            "Source URL": "https://example.com/story",
            "Status": "New",
        }
    )

    fields = mock_post.call_args.kwargs["json"]["fields"]
    assert len(fields["Created At"]) == 10
    assert fields["Created At"].count("-") == 2


def test_raise_for_status_truncates_response_body_by_default():
    resp = MagicMock()
    resp.text = "x" * 300
    resp.raise_for_status.side_effect = requests.HTTPError("bad request")

    with pytest.raises(requests.HTTPError) as exc_info:
        _raise_for_status(resp)

    assert f"response={'x' * 200}" in str(exc_info.value)
    assert "x" * 201 not in str(exc_info.value)


def test_raise_for_status_allows_opt_in_verbose_response_body():
    resp = MagicMock()
    resp.text = "x" * 300
    resp.raise_for_status.side_effect = requests.HTTPError("bad request")

    with pytest.raises(requests.HTTPError) as exc_info:
        _raise_for_status(resp, body_limit=300)

    assert f"response={'x' * 300}" in str(exc_info.value)
