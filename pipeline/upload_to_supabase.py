"""
CafeSelect — Upload DB records to Supabase
==========================================
Reads data/db_records/cafes.json and upserts all records into the Supabase
`cafes` table. Uses place_id as the conflict key so re-runs are safe.

Usage (from Workspace/):
    python pipeline/upload_to_supabase.py
    python pipeline/upload_to_supabase.py --dry-run
    python pipeline/upload_to_supabase.py --cafe "Cafe Belen"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).parent
_WORKSPACE = _HERE.parent

sys.path.insert(0, str(_HERE))
from config import settings, require  # noqa: E402

from supabase import create_client  # noqa: E402

DB_RECORDS = _WORKSPACE / "data" / "db_records" / "cafes.json"

EXCLUDE_FIELDS = {"latitude", "longitude", "phone", "primary_type", "business_status"}


def load_records(cafe_name: str | None = None) -> list[dict]:
    records = json.loads(DB_RECORDS.read_text())
    if cafe_name:
        records = [r for r in records if r.get("name") == cafe_name]
    return records


def clean(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in EXCLUDE_FIELDS and v is not None}


def upload(dry_run: bool = False, cafe_name: str | None = None) -> None:
    url = require("SUPABASE_URL", settings.supabase_url)
    key = settings.supabase_key or settings.supabase_service_key
    require("SUPABASE_KEY or SUPABASE_SERVICE_KEY", key)

    records = load_records(cafe_name)
    if not records:
        print("No records found.")
        return

    print(f"{'[DRY RUN] ' if dry_run else ''}Uploading {len(records)} cafe(s)...")

    if dry_run:
        for r in records:
            print(f"  {r.get('name')} ({r.get('place_id')})")
        return

    client = create_client(url, key)
    cleaned = [clean(r) for r in records]

    response = (
        client.table("cafes")
        .upsert(cleaned, on_conflict="place_id")
        .execute()
    )

    uploaded = len(response.data) if response.data else 0
    print(f"Done. {uploaded} record(s) upserted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print records without uploading")
    parser.add_argument("--cafe", help="Upload only this cafe by name")
    args = parser.parse_args()
    upload(dry_run=args.dry_run, cafe_name=args.cafe)
