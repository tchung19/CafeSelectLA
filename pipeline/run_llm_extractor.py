"""
CafeSelect — Run LLM Attribute Extraction on saved cafe data
=============================================================
Reads each cafe directory under a data root, loads details.json, and
produces llm_attributes.json via Claude Haiku 4.5.

Skips cafes that already have llm_attributes.json unless --force is passed.

Usage:
    python pipeline/run_llm_extractor.py --data-dir data/cafes/
    python pipeline/run_llm_extractor.py --data-dir data/cafes/ --force
    python pipeline/run_llm_extractor.py --data-dir data/cafes/ --cafe 01_Upside_Down
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import time
from datetime import datetime
from pathlib import Path

from llm_extractor import extract_attributes


def _iter_cafe_dirs(data_dir: str, cafe_filter: str | None) -> list[Path]:
    root = Path(data_dir)
    dirs = sorted(
        Path(d) for d in glob.glob(str(root / "*"))
        if os.path.isdir(d)
    )
    if cafe_filter:
        key = cafe_filter.lower()
        dirs = [d for d in dirs if key in d.name.lower()]
    return dirs


def run(data_dir: str, force: bool = False, cafe_filter: str | None = None) -> None:
    cafe_dirs = _iter_cafe_dirs(data_dir, cafe_filter)
    if not cafe_dirs:
        print(f"❌ No cafe folders found in {data_dir}")
        return

    print(f"\n{'=' * 60}")
    print(f"  LLM Attribute Extraction — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  {len(cafe_dirs)} cafes  |  data_dir={data_dir}  |  force={force}")
    print(f"{'=' * 60}\n")

    totals = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}
    skipped = 0

    for i, cafe_dir in enumerate(cafe_dirs, 1):
        folder = cafe_dir.name
        out_path = cafe_dir / "llm_attributes.json"

        if out_path.exists() and not force:
            print(f"  [{i}/{len(cafe_dirs)}] {folder}: already done, skipping (use --force to re-run)")
            skipped += 1
            continue

        details_path = cafe_dir / "details.json"
        if not details_path.exists():
            print(f"  [{i}/{len(cafe_dirs)}] {folder}: no details.json, skipping")
            continue

        with open(details_path) as f:
            details = json.load(f)

        name = details.get("displayName", {}).get("text", folder)
        reviews = details.get("reviews", [])
        gen_summary = details.get("generativeSummary", {}) or {}
        rev_summary = details.get("reviewSummary", {}) or {}
        hood_summary = details.get("neighborhoodSummary", {}) or {}

        gen_overview    = gen_summary.get("overview", {}).get("text", "")
        gen_description = gen_summary.get("description", {}).get("text", "")
        rev_summary_text  = rev_summary.get("text", {}).get("text", "")
        hood_summary_text = hood_summary.get("text", {}).get("text", "")

        print(f"  [{i}/{len(cafe_dirs)}] {name}")

        try:
            result = extract_attributes(
                cafe_name=name,
                reviews=reviews,
                gen_overview=gen_overview,
                gen_description=gen_description,
                review_summary=rev_summary_text,
                neighborhood_summary=hood_summary_text,
            )
        except Exception as e:
            print(f"    ❌ failed: {type(e).__name__}: {e}")
            continue

        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        u = result["usage"]
        totals["in"]          += u["input_tokens"]
        totals["out"]         += u["output_tokens"]
        totals["cache_read"]  += u["cache_read_input_tokens"]
        totals["cache_write"] += u["cache_creation_input_tokens"]

        print(
            f"    ✅ in={u['input_tokens']}  out={u['output_tokens']}  "
            f"cache_read={u['cache_read_input_tokens']}  cache_write={u['cache_creation_input_tokens']}"
        )
        time.sleep(0.3)

    processed = len(cafe_dirs) - skipped
    print(f"\n{'=' * 60}")
    print(f"  Processed: {processed}  Skipped: {skipped}")
    print(f"  Totals: in={totals['in']}  out={totals['out']}  "
          f"cache_read={totals['cache_read']}  cache_write={totals['cache_write']}")
    # Haiku 4.5 pricing: $1/1M input, $5/1M output, cache_read ~0.1× input, cache_write ~1.25× input
    cost = (
        totals["in"]          * 1.00 / 1_000_000
        + totals["out"]       * 5.00 / 1_000_000
        + totals["cache_read"] * 0.10 / 1_000_000
        + totals["cache_write"] * 1.25 / 1_000_000
    )
    print(f"  Est cost: ${cost:.4f}")
    print(f"{'=' * 60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Claude Haiku LLM extraction on saved cafe details.json files."
    )
    parser.add_argument("--data-dir", "-d", required=True, metavar="DIR",
                        help="Root directory containing cafe subdirectories")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Re-run even if llm_attributes.json already exists")
    parser.add_argument("--cafe", metavar="NAME",
                        help="Only process cafes whose folder name contains NAME")
    args = parser.parse_args()

    run(data_dir=args.data_dir, force=args.force, cafe_filter=args.cafe)


if __name__ == "__main__":
    main()
