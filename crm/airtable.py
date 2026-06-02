"""Airtable CRM client — Contacts table and Manual DM Queue operations."""

import argparse
import logging
import uuid
from datetime import datetime, timezone

import requests

from crm.schema import CONTACTS_FIELDS, validate_lead, is_handcraft_required

_BASE_URL = "https://api.airtable.com/v0"
_TABLE_NAME = "Contacts"
_TIMEOUT = 20

logger = logging.getLogger(__name__)


def _raise_for_status(resp: requests.Response, *, body_limit: int = 200) -> None:
    """Raise HTTP errors with Airtable's response body attached."""
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        body = resp.text[:body_limit]
        raise requests.HTTPError(f"{exc}; response={body}", response=resp) from exc


def _escape(value: str) -> str:
    """Escape a string value for use inside an Airtable formula string literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


class AirtableClient:
    """Thin wrapper around the Airtable REST API for this pipeline's tables."""

    def __init__(self, pat: str, base_id: str, *, error_body_limit: int = 200):
        self._headers = {
            "Authorization": f"Bearer {pat}",
            "Content-Type": "application/json",
        }
        self._base_id = base_id
        self._table_url = f"{_BASE_URL}/{base_id}/{_TABLE_NAME}"
        self._error_body_limit = error_body_limit

    def _get(self, params: dict) -> list[dict]:
        records = []
        offset = None
        while True:
            if offset:
                params["offset"] = offset
            resp = requests.get(
                self._table_url, headers=self._headers, params=params, timeout=_TIMEOUT
            )
            _raise_for_status(resp, body_limit=self._error_body_limit)
            body = resp.json()
            records.extend(body.get("records", []))
            offset = body.get("offset")
            if not offset:
                break
        return records

    def find_by_email(self, email: str) -> dict | None:
        """Return the first Contacts record matching email, or None."""
        formula = f"{{Email}}='{_escape(email)}'"
        records = self._get({"filterByFormula": formula, "maxRecords": 1})
        return records[0] if records else None

    def find_by_source_url(self, url: str) -> dict | None:
        """Return the first Contacts record matching source URL, or None."""
        formula = f"{{Source URL}}='{_escape(url)}'"
        records = self._get({"filterByFormula": formula, "maxRecords": 1})
        return records[0] if records else None

    def find_by_hunter_lead_id(self, lead_id: str) -> dict | None:
        """Return the first Contacts record matching Hunter Lead ID, or None."""
        formula = f"{{Hunter Lead ID}}='{_escape(lead_id)}'"
        records = self._get({"filterByFormula": formula, "maxRecords": 1})
        return records[0] if records else None

    def find_by_status(self, status: str) -> list[dict]:
        """Return all Contacts records with the given status."""
        formula = f"{{Status}}='{_escape(status)}'"
        return self._get({"filterByFormula": formula})

    def create_record(self, table_name: str, fields: dict) -> dict:
        """Create a new record in the named table. Returns the created record."""
        url = f"{_BASE_URL}/{self._base_id}/{table_name}"
        resp = requests.post(
            url, headers=self._headers, json={"fields": fields}, timeout=_TIMEOUT
        )
        _raise_for_status(resp, body_limit=self._error_body_limit)
        return resp.json()

    def upsert(self, lead: dict) -> dict:
        """Create or update a Contacts record, keyed on Source URL."""
        errors = validate_lead(lead)
        if errors:
            raise ValueError(f"Lead validation failed: {errors}")

        lead.setdefault("Requires Handcraft", is_handcraft_required(lead))
        lead.setdefault("Status", "New")
        lead.setdefault("Created At", datetime.now(timezone.utc).date().isoformat())

        # Only send fields Airtable knows about
        fields = {
            k: v for k, v in lead.items() if k in CONTACTS_FIELDS and v is not None
        }

        existing = self.find_by_source_url(lead.get("Source URL", ""))
        if existing:
            return self.update(existing["id"], fields)

        resp = requests.post(
            self._table_url,
            headers=self._headers,
            json={"fields": fields},
            timeout=_TIMEOUT,
        )
        _raise_for_status(resp, body_limit=self._error_body_limit)
        return resp.json()

    def update(self, record_id: str, fields: dict) -> dict:
        """PATCH specific fields on an existing Contacts record."""
        resp = requests.patch(
            f"{self._table_url}/{record_id}",
            headers=self._headers,
            json={"fields": fields},
            timeout=_TIMEOUT,
        )
        _raise_for_status(resp, body_limit=self._error_body_limit)
        return resp.json()

    def list_manual_queue(self, channel: str | None = None) -> list[dict]:
        """Return all Manual DM Queue records, optionally filtered by channel."""
        url = f"{_BASE_URL}/{self._base_id}/Manual DM Queue"
        params = {}
        if channel:
            params["filterByFormula"] = f"{{Channel}}='{_escape(channel)}'"
        resp = requests.get(url, headers=self._headers, params=params, timeout=_TIMEOUT)
        _raise_for_status(resp, body_limit=self._error_body_limit)
        return resp.json().get("records", [])

    def add_to_manual_queue(self, fields: dict) -> dict:
        """Create a new record in the Manual DM Queue table."""
        return self.create_record("Manual DM Queue", fields)

    def mark_dm_sent(self, record_id: str) -> dict:
        """Set Status='Sent' on a Manual DM Queue record."""
        url = f"{_BASE_URL}/{self._base_id}/Manual DM Queue/{record_id}"
        resp = requests.patch(
            url,
            headers=self._headers,
            json={"fields": {"Status": "Sent"}},
            timeout=_TIMEOUT,
        )
        _raise_for_status(resp, body_limit=self._error_body_limit)
        return resp.json()


def get_client(*, error_body_limit: int = 200) -> AirtableClient:
    """Return a fully configured AirtableClient using env-loaded credentials."""
    from config.settings import require_env

    return AirtableClient(
        require_env("AIRTABLE_PAT"),
        require_env("AIRTABLE_BASE_ID"),
        error_body_limit=error_body_limit,
    )


def _smoke_test_contact(run_id: str) -> dict:
    """Build a clearly synthetic Contacts smoke-test lead."""
    return {
        "Name": "BOOK PIPELINE SMOKE TEST - Synthetic SerpApi Lead",
        "First Name": "Smoke",
        "Last Name": "Test",
        "Archetype": "bluecollar",
        "Source": "serpapi",
        "Source URL": f"https://example.com/book-pipeline/airtable-smoke/{run_id}",
        "City": "Detroit",
        "Date Window": "airtable_smoke",
        "Claude Score": 8,
        "Story Summary": (
            "Synthetic Airtable smoke test lead; not a real prospect."
        ),
        "Turning Point": "Synthetic test record created to validate Airtable writes.",
        "Email": "smoke-test@example.com",
        "Email Confidence": 100,
        "Contact Method": "email",
        "Contact Value": "smoke-test@example.com",
        "Status": "New",
    }


def _smoke_test_manual_queue_fields(run_id: str) -> dict:
    """Build a clearly synthetic Manual DM Queue smoke-test record."""
    return {
        "Source URL": f"https://example.com/book-pipeline/manual-queue-smoke/{run_id}",
        "Channel": "Manual Email",
        "Archetype": "bluecollar",
        "Name": "BOOK PIPELINE SMOKE TEST - Manual Queue",
        "Contact Method": "email",
        "Contact Value": "smoke-test@example.com",
        "Status": "Pending",
        "Notes": "Synthetic manual queue smoke test; not a real prospect.",
    }


def run_smoke_test() -> dict:
    """Write and read back synthetic Airtable records using configured credentials."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{run_id}-{uuid.uuid4().hex[:8]}"
    client = get_client(error_body_limit=1000)

    contact = _smoke_test_contact(run_id)
    contact_result = client.upsert(contact)
    contact_readback = client.find_by_source_url(contact["Source URL"])
    if contact_readback is None:
        raise RuntimeError("Contacts smoke-test readback failed")

    queue_fields = _smoke_test_manual_queue_fields(run_id)
    queue_result = client.add_to_manual_queue(queue_fields)
    queue_readback_records = client.list_manual_queue(channel=queue_fields["Channel"])
    queue_readback = next(
        (
            record
            for record in queue_readback_records
            if record.get("id") == queue_result.get("id")
            or record.get("fields", {}).get("Source URL") == queue_fields["Source URL"]
        ),
        None,
    )
    if queue_readback is None:
        raise RuntimeError("Manual DM Queue smoke-test readback failed")

    result = {
        "run_id": run_id,
        "contacts_record_id": contact_result.get("id"),
        "contacts_readback_id": contact_readback.get("id"),
        "manual_queue_record_id": queue_result.get("id"),
        "manual_queue_readback_id": queue_readback.get("id"),
        "contacts_source_url": contact["Source URL"],
    }
    logger.info("Airtable smoke test complete: %s", result)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Airtable CRM utilities.")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Write/read synthetic Contacts and Manual DM Queue records.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if args.smoke_test:
        smoke_result = run_smoke_test()
        print("=== Airtable Smoke Test ===")
        for key, value in smoke_result.items():
            print(f"{key}: {value}")
    else:
        raise SystemExit("No action requested. Use --smoke-test.")
