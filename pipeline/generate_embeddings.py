"""
CafeSelect — Generate & Store Cafe Embeddings
==============================================
Builds a text blob per cafe from vibe/decor/summary fields, embeds with
OpenAI text-embedding-3-small, and upserts the vector into Supabase.

Prerequisites — run once in Supabase SQL editor:
    create extension if not exists vector;
    alter table cafes add column if not exists embedding vector(1536);

Usage (from Workspace/):
    python pipeline/generate_embeddings.py
    python pipeline/generate_embeddings.py --dry-run      # print blobs, no API calls
    python pipeline/generate_embeddings.py --cafe "Alfred Coffee"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).parent
_WORKSPACE = _HERE.parent

sys.path.insert(0, str(_HERE))
from config import settings, require  # noqa: E402

from openai import OpenAI  # noqa: E402
from supabase import create_client  # noqa: E402

DB_RECORDS = _WORKSPACE / "data" / "db_records" / "cafes.json"
EMBED_MODEL = "text-embedding-3-small"


def build_text(cafe: dict) -> str:
    """Construct a rich text blob from a cafe record for embedding."""
    parts = []

    name = cafe.get("name") or ""
    neighborhood = cafe.get("neighborhood") or ""
    if name or neighborhood:
        parts.append(f"{name} · {neighborhood}")

    vibe = cafe.get("overall_vibe") or []
    if vibe:
        parts.append(", ".join(vibe))

    decor = cafe.get("decor_style") or []
    if decor:
        parts.append(", ".join(decor))

    noise = cafe.get("noise_level")
    if noise:
        parts.append(f"{noise} noise level")

    drinks = cafe.get("specialty_drinks") or []
    if drinks:
        parts.append("drinks: " + ", ".join(drinks))

    items = cafe.get("signature_items") or []
    if items:
        parts.append("food: " + ", ".join(items))

    for field in ("generative_summary", "review_summary"):
        text = cafe.get(field)
        if text:
            parts.append(text)
            break  # one summary is enough

    best_time = cafe.get("best_time_to_visit")
    if best_time:
        parts.append(best_time)

    return " · ".join(parts)


def generate_embeddings(dry_run: bool = False, cafe_name: str | None = None) -> None:
    require("OPENAI_API_KEY", settings.openai_api_key)
    url = require("SUPABASE_URL", settings.supabase_url)
    key = settings.supabase_key or settings.supabase_service_key
    require("SUPABASE_KEY or SUPABASE_SERVICE_KEY", key)

    cafes = json.loads(DB_RECORDS.read_text())
    if cafe_name:
        cafes = [c for c in cafes if c.get("name") == cafe_name]

    if not cafes:
        print("No cafes found.")
        return

    print(f"{'[DRY RUN] ' if dry_run else ''}Embedding {len(cafes)} cafe(s) with {EMBED_MODEL}...\n")

    if dry_run:
        for cafe in cafes:
            print(f"── {cafe.get('name')}")
            print(f"   {build_text(cafe)}\n")
        return

    openai = OpenAI(api_key=settings.openai_api_key)
    supabase = create_client(url, key)

    total_tokens = 0

    for i, cafe in enumerate(cafes, 1):
        place_id = cafe.get("place_id")
        if not place_id:
            print(f"  [{i}/{len(cafes)}] skipping — no place_id")
            continue

        text = build_text(cafe)
        response = openai.embeddings.create(model=EMBED_MODEL, input=text)
        vector = response.data[0].embedding
        total_tokens += response.usage.total_tokens

        supabase.table("cafes").update({"embedding": vector}).eq("place_id", place_id).execute()
        print(f"  [{i}/{len(cafes)}] {cafe.get('name')} ✅  ({len(text)} chars)")

        if i < len(cafes):
            time.sleep(0.05)

    cost = total_tokens * 0.00000002  # $0.020 per 1M tokens
    print(f"\n✅ Done. {total_tokens:,} tokens used — est. cost ${cost:.5f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print text blobs without calling OpenAI")
    parser.add_argument("--cafe", help="Embed only this cafe by name")
    args = parser.parse_args()
    generate_embeddings(dry_run=args.dry_run, cafe_name=args.cafe)
