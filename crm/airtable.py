import os
import requests
from datetime import datetime, timezone
from typing import Optional

from crm.schema import CONTACTS_FIELDS, validate_lead, is_handcraft_required

_BASE_URL = "https://api.airtable.com/v0"
_TABLE_NAME = "Contacts"


class AirtableClient:
    def __init__(self, pat: str, base_id: str):
        self._headers = {
            "Authorization": f"Bearer {pat}",
            "Content-Type": "application/json",
        }
        self._base_id = base_id
        self._table_url = f"{_BASE_URL}/{base_id}/{_TABLE_NAME}"

    def _get(self, params: dict) -> list[dict]:
        records = []
        offset = None
        while True:
            if offset:
                params['offset'] = offset
            resp = requests.get(self._table_url, headers=self._headers, params=params)
            resp.raise_for_status()
            body = resp.json()
            records.extend(body.get('records', []))
            offset = body.get('offset')
            if not offset:
                break
        return records

    def find_by_email(self, email: str) -> Optional[dict]:
        formula = f"{{Email}}='{email}'"
        records = self._get({'filterByFormula': formula, 'maxRecords': 1})
        return records[0] if records else None

    def find_by_source_url(self, url: str) -> Optional[dict]:
        formula = f"{{Source URL}}='{url}'"
        records = self._get({'filterByFormula': formula, 'maxRecords': 1})
        return records[0] if records else None

    def find_by_status(self, status: str) -> list[dict]:
        formula = f"{{Status}}='{status}'"
        return self._get({'filterByFormula': formula})

    def create_record(self, table_name: str, fields: dict) -> dict:
        url = f"{_BASE_URL}/{self._base_id}/{table_name}"
        resp = requests.post(url, headers=self._headers, json={"fields": fields})
        resp.raise_for_status()
        return resp.json()

    def upsert(self, lead: dict) -> dict:
        """Create or update a Contacts record, keyed on Source URL."""
        errors = validate_lead(lead)
        if errors:
            raise ValueError(f"Lead validation failed: {errors}")

        lead.setdefault('Requires Handcraft', is_handcraft_required(lead))
        lead.setdefault('Status', 'New')
        lead.setdefault('Created At', datetime.now(timezone.utc).isoformat())

        # Only send fields Airtable knows about
        fields = {k: v for k, v in lead.items() if k in CONTACTS_FIELDS and v is not None}

        existing = self.find_by_source_url(lead.get('Source URL', ''))
        if existing:
            return self.update(existing['id'], fields)

        resp = requests.post(
            self._table_url,
            headers=self._headers,
            json={"fields": fields},
        )
        resp.raise_for_status()
        return resp.json()

    def update(self, record_id: str, fields: dict) -> dict:
        resp = requests.patch(
            f"{self._table_url}/{record_id}",
            headers=self._headers,
            json={"fields": fields},
        )
        resp.raise_for_status()
        return resp.json()

    def list_manual_queue(self, channel: Optional[str] = None) -> list[dict]:
        url = f"{_BASE_URL}/{self._base_id}/Manual DM Queue"
        params = {}
        if channel:
            params['filterByFormula'] = f"{{Channel}}='{channel}'"
        resp = requests.get(url, headers=self._headers, params=params)
        resp.raise_for_status()
        return resp.json().get('records', [])

    def add_to_manual_queue(self, fields: dict) -> dict:
        return self.create_record('Manual DM Queue', fields)

    def mark_dm_sent(self, record_id: str) -> dict:
        url = f"{_BASE_URL}/{self._base_id}/Manual DM Queue/{record_id}"
        resp = requests.patch(
            url, headers=self._headers, json={"fields": {"Status": "Sent"}}
        )
        resp.raise_for_status()
        return resp.json()


def get_client() -> AirtableClient:
    from config.settings import AIRTABLE_PAT, AIRTABLE_BASE_ID
    return AirtableClient(AIRTABLE_PAT, AIRTABLE_BASE_ID)
