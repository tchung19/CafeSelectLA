"""
CafeSelect — Pipeline Orchestrator
====================================
End-to-end pipeline for processing one or more cafes:
  1. Fetch Google Places details + photos (google_places.py)
  2. Run Vision Pass A — per-photo GPT-4o (vision_pass_a.py)
  3. Run Vision Pass B — Claude Sonnet aggregator (vision_pass_b.py)
  4. Run LLM attribute extraction — Claude Haiku (llm_extractor.py)
  5. Build merged DB record (db_builder.py)

Usage:
    # Full pipeline on a list of place_ids:
    python pipeline/pipeline.py --place-ids ChIJ... ChIJ... --data-dir data/cafes/ --db-dir data/db_records/

    # Skip steps already done (idempotent by default):
    python pipeline/pipeline.py --place-ids ChIJ... --data-dir data/cafes/ --db-dir data/db_records/

    # Force re-run all steps:
    python pipeline/pipeline.py --place-ids ChIJ... --data-dir data/cafes/ --db-dir data/db_records/ --force

    # Run only specific steps on already-fetched data:
    python pipeline/pipeline.py --data-dir data/cafes/ --db-dir data/db_records/ --skip-fetch

    # Read place_ids from a JSON file (output of discover.py):
    python pipeline/pipeline.py --ids-file new_ids.json --data-dir data/cafes/ --db-dir data/db_records/
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

# primary_type values that are clearly not cafes — skip vision + LLM to save cost
NON_CAFE_TYPES = {
    "restaurant", "fast_food_restaurant", "meal_takeaway", "meal_delivery",
    "pizza_restaurant", "sushi_restaurant", "ramen_restaurant",
    "hamburger_restaurant", "sandwich_shop", "seafood_restaurant",
    "steak_house", "chinese_restaurant", "japanese_restaurant",
    "korean_restaurant", "thai_restaurant", "mexican_restaurant",
    "grocery_store", "supermarket", "convenience_store",
    "breakfast_restaurant", "brunch_restaurant",
    "pharmacy", "drugstore", "gas_station", "hotel", "lodging",
    "hospital", "doctor", "dentist", "museum", "bar", "night_club",
}

import google_places as gp
from vision_pass_a import run_pass_a
from vision_pass_b import run_pass_b, load_per_photo_dir
from run_llm_extractor import run as run_llm
from db_builder import run as run_db_build, build_record, completeness, _resolve_vision, _load_json
from regions import extract_neighborhood
from upload_to_supabase import upload as upload_to_supabase
from generate_embeddings import generate_embeddings


# ── Single-cafe orchestrator ──────────────────────────────────────────────────

def process_cafe(
    place_id: str,
    data_dir: Path,
    force: bool = False,
    skip_fetch: bool = False,
    skip_vision: bool = False,
    skip_llm: bool = False,
    max_photos: int = 10,
) -> dict | None:
    """
    Run the full pipeline for one place_id.
    Returns the final DB record dict, or None on failure.
    """
    # ── Step 1: Fetch ──────────────────────────────────────────────────────────
    details = None
    cafe_dir: Path | None = None

    if not skip_fetch:
        print(f"    [1/5] Fetching Google Places details...")
        try:
            folder_name, details = gp.fetch_and_save_cafe(
                place_id=place_id,
                output_dir=data_dir,
                max_photos=max_photos,
            )
            cafe_dir = data_dir / folder_name
            print(f"    ✅ Saved → {cafe_dir.name}")
        except Exception as e:
            print(f"    ❌ Fetch failed: {e}")
            return None
    else:
        # Find existing folder by scanning for details.json with matching place_id
        for d in sorted(data_dir.iterdir()):
            if not d.is_dir():
                continue
            dj = d / "details.json"
            if not dj.exists():
                continue
            with open(dj) as f:
                data = json.load(f)
            if data.get("id") == place_id:
                cafe_dir = d
                details  = data
                break

        if cafe_dir is None:
            print(f"    ❌ --skip-fetch: no existing folder found for {place_id}")
            return None

    # Load details if not already loaded
    if details is None:
        details_path = cafe_dir / "details.json"
        if not details_path.exists():
            print(f"    ❌ details.json missing for {cafe_dir.name}")
            return None
        with open(details_path) as f:
            details = json.load(f)

    cafe_name = details.get("displayName", {}).get("text", cafe_dir.name)

    # ── Primary type gate — skip expensive steps for non-cafes ────────────────
    primary_type = details.get("primaryType", "") or ""
    if primary_type in NON_CAFE_TYPES:
        print(f"    ⏭️  Skipping — primary_type={primary_type} is not a cafe")
        return None

    # ── Step 2+3: Vision ───────────────────────────────────────────────────────
    if not skip_vision:
        photos_dir = cafe_dir / "photos"
        if not photos_dir.exists() or not list(photos_dir.glob("photo_*.jpg")):
            print(f"    ⚠️  No photos found — skipping vision passes")
        else:
            per_photo_dir = cafe_dir / "per_photo"

            if not force and (cafe_dir / "v2_aggregate.json").exists():
                print(f"    [2/5] Vision Pass A — skipping (already done)")
                print(f"    [3/5] Vision Pass B — skipping (already done)")
            else:
                print(f"    [2/5] Vision Pass A (per-photo GPT-4o)...")
                try:
                    per_photo_results, usage_a = run_pass_a(cafe_dir, cafe_dir)
                    cost_a = (usage_a["prompt_tokens"] * 2.50 + usage_a["completion_tokens"] * 10.00) / 1_000_000
                    print(f"    ✅ Pass A done — {len(per_photo_results)} photos, ${cost_a:.4f}")
                except Exception as e:
                    print(f"    ❌ Pass A failed: {e}")
                    per_photo_results = None

                if per_photo_results is not None:
                    print(f"    [3/5] Vision Pass B (Claude Sonnet aggregator)...")
                    try:
                        v2_result, usage_b = run_pass_b(cafe_name, per_photo_results, cafe_dir)
                        cost_b = (usage_b["input_tokens"] * 3.00 + usage_b["output_tokens"] * 15.00) / 1_000_000
                        print(f"    ✅ Pass B done — ${cost_b:.4f}")
                    except Exception as e:
                        print(f"    ❌ Pass B failed: {e}")
    else:
        print(f"    [2/5] Vision Pass A — skipped")
        print(f"    [3/5] Vision Pass B — skipped")

    # ── Step 4: LLM extraction ─────────────────────────────────────────────────
    if not skip_llm:
        out_path = cafe_dir / "llm_attributes.json"
        if not force and out_path.exists():
            print(f"    [4/5] LLM extraction — skipping (already done)")
        else:
            print(f"    [4/5] LLM extraction (Claude Haiku)...")
            try:
                run_llm(data_dir=str(data_dir), force=force, cafe_filter=cafe_dir.name)
                print(f"    ✅ LLM extraction done")
            except Exception as e:
                print(f"    ❌ LLM extraction failed: {e}")
    else:
        print(f"    [4/5] LLM extraction — skipped")

    # ── Step 5: Build DB record ────────────────────────────────────────────────
    print(f"    [5/5] Building DB record...")
    llm_wrapper    = _load_json(cafe_dir / "llm_attributes.json")
    vision_wrapper = _resolve_vision(cafe_dir)

    if not llm_wrapper:
        print(f"    ⚠️  No llm_attributes.json — record will have null LLM fields")
    if not vision_wrapper:
        print(f"    ⚠️  No vision JSON — record will have null vision fields")

    rec = build_record(details, llm_wrapper, vision_wrapper)
    comp = completeness(rec)
    filled_total = sum(int(v.split("/")[0]) for v in comp.values())
    all_total    = sum(int(v.split("/")[1]) for v in comp.values())
    pct = 100 * filled_total / all_total if all_total else 0
    print(f"    ✅ Record built — {filled_total}/{all_total} fields ({pct:.0f}% complete)")

    return rec


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CafeSelect end-to-end pipeline: fetch → vision → LLM → DB record."
    )

    id_group = parser.add_mutually_exclusive_group()
    id_group.add_argument("--place-ids", nargs="+", metavar="ID",
                          help="One or more Google place_ids to process")
    id_group.add_argument("--ids-file", metavar="FILE",
                          help="JSON file containing [{place_id, ...}, ...] from discover.py")

    parser.add_argument("--data-dir", "-d", required=True, metavar="DIR",
                        help="Root directory where cafe folders are stored")
    parser.add_argument("--db-dir", required=True, metavar="DIR",
                        help="Output directory for final DB records")
    parser.add_argument("--force", action="store_true",
                        help="Re-run all steps even if outputs already exist")
    parser.add_argument("--skip-fetch",  action="store_true", help="Skip Google Places fetch")
    parser.add_argument("--skip-vision", action="store_true", help="Skip vision passes")
    parser.add_argument("--skip-llm",    action="store_true", help="Skip LLM extraction")
    parser.add_argument("--max-photos", type=int, default=10, metavar="N",
                        help="Max photos to download per cafe (default: 10)")
    parser.add_argument("--sleep", type=float, default=1.0, metavar="SEC",
                        help="Sleep between cafes in seconds (default: 1.0)")

    args = parser.parse_args()

    if not args.place_ids and not args.ids_file and not args.skip_fetch:
        parser.error("Provide --place-ids or --ids-file (or --skip-fetch to process existing data only)")

    data_dir = Path(args.data_dir)
    db_dir   = Path(args.db_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    # Resolve place_ids list
    place_ids: list[str] = []
    if args.place_ids:
        place_ids = args.place_ids
    elif args.ids_file:
        with open(args.ids_file) as f:
            entries = json.load(f)
        place_ids = [e["place_id"] for e in entries if e.get("place_id")]
    elif args.skip_fetch:
        # Process all existing cafe dirs
        place_ids = []  # handled below

    print(f"\n{'=' * 60}")
    print(f"  CafeSelect Pipeline — {datetime.now():%Y-%m-%d %H:%M:%S}")
    if place_ids:
        print(f"  {len(place_ids)} cafes to process")
    else:
        print(f"  Processing all existing cafes in {data_dir}")
    print(f"{'=' * 60}\n")

    records: list[dict] = []

    if args.skip_fetch and not place_ids:
        # Process every existing cafe dir
        for cafe_dir in sorted(data_dir.iterdir()):
            if not cafe_dir.is_dir():
                continue
            dj = cafe_dir / "details.json"
            if not dj.exists():
                continue
            with open(dj) as f:
                pid = json.load(f).get("id", "")
            if pid:
                place_ids.append(pid)

    for i, place_id in enumerate(place_ids, 1):
        print(f"[{i}/{len(place_ids)}] {place_id}")
        rec = process_cafe(
            place_id=place_id,
            data_dir=data_dir,
            force=args.force,
            skip_fetch=args.skip_fetch,
            skip_vision=args.skip_vision,
            skip_llm=args.skip_llm,
            max_photos=args.max_photos,
        )
        if rec:
            records.append(rec)
        print()

        if i < len(place_ids):
            time.sleep(args.sleep)

    # Write combined — merge with existing records, keyed by place_id
    all_path = db_dir / "cafes.json"
    existing: dict[str, dict] = {}
    if all_path.exists():
        with open(all_path) as f:
            for r in json.load(f):
                if r.get("place_id"):
                    existing[r["place_id"]] = r
    for r in records:
        if r.get("place_id"):
            existing[r["place_id"]] = r
    merged = list(existing.values())
    with open(all_path, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f"{'=' * 60}")
    print(f"✅ Done — {len(records)}/{len(place_ids)} cafes processed")
    print(f"   Records → {db_dir}/cafes.json")
    print(f"{'=' * 60}\n")

    print("Uploading to Supabase...")
    upload_to_supabase()
    print("✅ Supabase upload complete\n")

    print("Generating embeddings...")
    generate_embeddings()
    print("✅ Embeddings complete\n")


if __name__ == "__main__":
    main()
