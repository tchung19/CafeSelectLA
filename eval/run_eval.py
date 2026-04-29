"""
CafeSelect Eval Runner
=======================
Usage:
    python eval/run_eval.py                    # run both labeling + search eval
    python eval/run_eval.py --labeling         # only labeling eval
    python eval/run_eval.py --search           # only search eval
    python eval/run_eval.py --id 3             # single search case
    python eval/run_eval.py --category study   # search cases in one category
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from Workspace root
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.test_data import LABELING_GROUND_TRUTH, SEARCH_GROUND_TRUTH
from api.query_parser import parse_query
from api.search import run_search, run_embedding_search, _supabase, RETURN_COLS


# ── Helpers ───────────────────────────────────────────────────────────────────

def _name_match(actual: str, expected: str) -> bool:
    return expected.lower() in actual.lower() or actual.lower() in expected.lower()


def _fetch_cafe_by_name(name: str) -> dict | None:
    rows = (
        _supabase.table("cafes")
        .select(RETURN_COLS)
        .ilike("name", f"%{name}%")
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


# ── Labeling eval ─────────────────────────────────────────────────────────────

def run_labeling_eval() -> tuple[int, int]:
    """Returns (correct_count, total_count)."""
    if not LABELING_GROUND_TRUTH:
        print("  (no labeling ground truth defined — add entries to test_data.py)")
        return 0, 0

    correct = 0
    total = 0

    for entry in LABELING_GROUND_TRUTH:
        cafe_name = entry["cafe_name"]
        expected_attrs = entry["attributes"]

        print(f"\n{cafe_name}")
        record = _fetch_cafe_by_name(cafe_name)
        if record is None:
            print(f"  ⚠️  Not found in DB — skipping")
            continue

        for attr, expected_val in expected_attrs.items():
            actual_val = record.get(attr)
            total += 1

            # has_outlets is stored as int; treat > 0 as True
            if attr == "has_outlets" and expected_val is True:
                match = bool(actual_val and actual_val > 0)
                actual_display = f"{actual_val} (int)"
            else:
                match = actual_val == expected_val
                actual_display = repr(actual_val)

            if match:
                correct += 1
                print(f"  ✅ {attr}: {actual_display}")
            else:
                print(f"  ❌ {attr}: {actual_display}  (expected {expected_val!r})")

    return correct, total


# ── Search eval ───────────────────────────────────────────────────────────────

def run_search_eval(
    case_id: int | None = None,
    category: str | None = None,
) -> tuple[int, int]:
    """Returns (passed_count, total_count)."""
    cases = SEARCH_GROUND_TRUTH

    if case_id is not None:
        cases = [c for c in cases if c["id"] == case_id]
    if category is not None:
        cases = [c for c in cases if c.get("category") == category]

    if not cases:
        print("  (no matching search cases — add entries to test_data.py)")
        return 0, 0

    passed = 0

    for case in cases:
        qid = case["id"]
        query = case["query"]
        expected = case["expected"]
        min_hits = case.get("min_hits", 1)
        cat = case.get("category", "")

        print(f"\n[{qid}] \"{query}\"  [{cat}]")

        # Parse
        filters = parse_query(query)
        search_mode = filters.pop("search_mode", "filter")
        filters["limit"] = 20  # wide net to avoid random.sample excluding expected cafes

        print(f"    Parsed → search_mode={search_mode}  filters={_short(filters)}")

        # Search
        if search_mode == "embedding":
            results = run_embedding_search(query, limit=20)
        elif search_mode == "hybrid":
            filter_results = run_search(dict(filters))
            embed_results = run_embedding_search(query, limit=20)
            seen = {r["place_id"] for r in filter_results}
            extras = [r for r in embed_results if r["place_id"] not in seen]
            results = (filter_results + extras)[:20]
        else:
            results = run_search(filters)

        result_names = [r["name"] for r in results]
        print(f"    Results: {len(results)} cafes returned")

        hits = 0
        for exp in expected:
            found = any(_name_match(actual, exp) for actual in result_names)
            if found:
                hits += 1
                print(f"    ✅ {exp} — found")
            else:
                print(f"    ❌ {exp} — MISSING")

        status = "PASS" if hits >= min_hits else "FAIL"
        print(f"    Score: {hits}/{len(expected)} hits (min {min_hits}) → {status}")
        if status == "PASS":
            passed += 1

    return passed, len(cases)


def _short(d: dict) -> str:
    """Compact repr of filter dict for display."""
    skip = {"limit"}
    return "  ".join(f"{k}={v}" for k, v in d.items() if k not in skip)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CafeSelect end-to-end eval")
    parser.add_argument("--labeling", action="store_true", help="Only run labeling eval")
    parser.add_argument("--search", action="store_true", help="Only run search eval")
    parser.add_argument("--id", type=int, help="Run a single search test case by ID")
    parser.add_argument("--category", help="Run search cases in one category")
    args = parser.parse_args()

    run_lab = not args.search or args.labeling
    run_srch = not args.labeling or args.search or args.id or args.category

    lab_correct = lab_total = 0
    srch_passed = srch_total = 0

    if run_lab and not args.id and not args.category:
        print("\n" + "=" * 50)
        print("  Labeling Eval")
        print("=" * 50)
        lab_correct, lab_total = run_labeling_eval()

    if run_srch:
        print("\n" + "=" * 50)
        print("  Search Eval")
        print("=" * 50)
        srch_passed, srch_total = run_search_eval(
            case_id=args.id,
            category=args.category,
        )

    print("\n" + "=" * 50)
    print("  Summary")
    print("=" * 50)
    if lab_total:
        pct = 100 * lab_correct // lab_total
        print(f"Labeling:  {lab_correct}/{lab_total} attributes correct ({pct}%)")
    if srch_total:
        pct = 100 * srch_passed // srch_total
        print(f"Search:    {srch_passed}/{srch_total} cases passed ({pct}%)")
    if not lab_total and not srch_total:
        print("No test cases found. Add entries to eval/test_data.py to get started.")
    print()


if __name__ == "__main__":
    main()
