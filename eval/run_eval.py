"""
CafeSelect Eval Runner
=======================
Usage:
    python eval/run_eval.py                    # run both labeling + search eval
    python eval/run_eval.py --labeling         # only labeling eval
    python eval/run_eval.py --search           # only search eval
    python eval/run_eval.py --db-quality       # only DB quality eval
    python eval/run_eval.py --id 3             # single search case
    python eval/run_eval.py --category study   # search cases in one category
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

# Allow running from Workspace root
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.test_data import LABELING_GROUND_TRUTH, SEARCH_GROUND_TRUTH
from api.query_parser import parse_query
from api.search import run_search, run_embedding_search, _supabase, RETURN_COLS, _DAY_COL, _parse_hours_range


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


# ── DB quality eval ───────────────────────────────────────────────────────────

# Columns to skip — always unique or always expected to be the same
_SKIP_COLS = {"place_id", "name", "address", "google_maps_url", "hero_photo_url", "website"}

NULL_THRESHOLD = 0.90      # >90% null → too sparse
DOMINANCE_THRESHOLD = 0.90 # >90% same value (excl. null) → low variance

def run_db_quality_eval() -> None:
    rows = _supabase.table("cafes").select("*").execute().data or []
    if not rows:
        print("  No rows found in DB.")
        return

    total = len(rows)
    print(f"\n  {total} cafes in DB\n")

    all_cols = [k for k in rows[0].keys() if k not in _SKIP_COLS]
    issues: list[str] = []

    for col in sorted(all_cols):
        values = [r.get(col) for r in rows]
        null_count = sum(1 for v in values if v is None)
        null_pct = null_count / total

        non_null = [v for v in values if v is not None]
        if non_null:
            # Stringify lists/dicts so they're hashable for Counter
            hashable = [str(v) if isinstance(v, (list, dict)) else v for v in non_null]
            most_common_val, most_common_count = Counter(hashable).most_common(1)[0]
            dominance_pct = most_common_count / total
        else:
            most_common_val, dominance_pct = None, 0.0

        if null_pct > NULL_THRESHOLD:
            flag = f"❌ {col}: {null_pct:.0%} null  ← too sparse"
            issues.append(flag)
            print(flag)
        elif dominance_pct > DOMINANCE_THRESHOLD:
            flag = f"⚠️  {col}: {dominance_pct:.0%} = {most_common_val!r}  ← low variance"
            issues.append(flag)
            print(flag)
        else:
            null_str = f"  {null_pct:.0%} null" if null_pct > 0.10 else ""
            print(f"  ✅ {col}{null_str}")

    print(f"\n  Column issues found: {len(issues)}")

    # ── Embedding coverage ────────────────────────────────────────────────────
    print("\n[Embedding coverage]")
    missing_embed = [r["name"] for r in rows if not r.get("embedding")]
    if not missing_embed:
        print(f"  ✅ All {total} cafes have embeddings")
    elif len(missing_embed) / total > 0.05:
        print(f"  ❌ {len(missing_embed)}/{total} missing embeddings ({len(missing_embed)/total:.0%})")
        for name in missing_embed[:10]:
            print(f"     • {name}")
        if len(missing_embed) > 10:
            print(f"     ... and {len(missing_embed) - 10} more")
    else:
        print(f"  ⚠️  {len(missing_embed)}/{total} missing embeddings:")
        for name in missing_embed:
            print(f"     • {name}")

    # ── Hours parseability ────────────────────────────────────────────────────
    print("\n[Hours parseability]")
    fully_broken, partially_broken = [], []
    for r in rows:
        day_results = [_parse_hours_range(r.get(col)) for col in _DAY_COL]
        non_null_days = [d for d, col in zip(day_results, _DAY_COL) if r.get(col)]
        failed = [col for col, parsed in zip(_DAY_COL, day_results) if r.get(col) and parsed is None]
        if failed:
            if len(failed) == len(non_null_days):
                fully_broken.append(r["name"])
            else:
                partially_broken.append((r["name"], failed))

    ok = total - len(fully_broken) - len(partially_broken)
    print(f"  ✅ {ok}/{total} cafes have fully parseable hours")
    if partially_broken:
        print(f"  ⚠️  {len(partially_broken)} cafes have ≥1 unparseable day:")
        for name, days in partially_broken[:5]:
            print(f"     • {name} — {', '.join(d.replace('hours_','') for d in days)}")
        if len(partially_broken) > 5:
            print(f"     ... and {len(partially_broken) - 5} more")
    if fully_broken:
        print(f"  ❌ {len(fully_broken)} cafes have ALL days unparseable:")
        for name in fully_broken:
            print(f"     • {name}")

    # ── Cross-field consistency ───────────────────────────────────────────────
    print("\n[Cross-field consistency]")
    contradictions = []
    for r in rows:
        name = r["name"]
        if r.get("study_friendly") is True and r.get("noise_level") == "loud":
            contradictions.append(f"{name} — study_friendly=True but noise_level=loud")
        if r.get("open_after_5pm") is True and all(not r.get(col) for col in _DAY_COL):
            contradictions.append(f"{name} — open_after_5pm=True but all hours null")

    if not contradictions:
        print(f"  ✅ No contradictions found")
    else:
        print(f"  ❌ {len(contradictions)} contradiction(s):")
        for c in contradictions:
            print(f"     • {c}")

    # ── Hero photo coverage ───────────────────────────────────────────────────
    print("\n[Hero photo coverage]")
    missing_photo = [r["name"] for r in rows if not r.get("hero_photo_url")]
    photo_pct = len(missing_photo) / total
    if photo_pct > 0.20:
        print(f"  ⚠️  {len(missing_photo)}/{total} cafes missing hero photo ({photo_pct:.0%})")
    else:
        print(f"  ✅ {total - len(missing_photo)}/{total} cafes have hero photo  ({len(missing_photo)} missing, {photo_pct:.0%})")
    for name in missing_photo[:5]:
        print(f"     • {name}")
    if len(missing_photo) > 5:
        print(f"     ... and {len(missing_photo) - 5} more")

    # ── Hidden cafes (low review count) ──────────────────────────────────────
    print("\n[Hidden cafes — review_count < 5]")
    hidden = [(r["name"], r.get("review_count", 0)) for r in rows if (r.get("review_count") or 0) < 5]
    if not hidden:
        print(f"  ✅ All cafes meet the review_count >= 5 threshold")
    else:
        print(f"  ⚠️  {len(hidden)} cafe(s) hidden from search:")
        for name, count in sorted(hidden, key=lambda x: x[1] or 0):
            print(f"     • {name} ({count} review{'s' if count != 1 else ''})")

    # ── Per-cafe completeness ─────────────────────────────────────────────────
    print("\n[Per-cafe completeness — key attributes]")
    KEY_ATTRS = [
        "study_friendly", "noise_level", "has_outlets", "good_for_dates",
        "has_matcha", "has_specialty_coffee", "has_patio", "has_vegan_options",
        "generative_summary", "overall_vibe", "neighborhood",
    ]
    incomplete = []
    for r in rows:
        filled = sum(1 for k in KEY_ATTRS if r.get(k) is not None)
        pct = filled / len(KEY_ATTRS)
        if pct < 0.50:
            incomplete.append((r["name"], filled, len(KEY_ATTRS)))
    if not incomplete:
        print(f"  ✅ All cafes have ≥50% of key attributes filled")
    else:
        print(f"  ⚠️  {len(incomplete)} cafe(s) below 50% completeness:")
        for name, filled, total_attrs in sorted(incomplete, key=lambda x: x[1]):
            print(f"     • {name} — {filled}/{total_attrs} fields ({filled/total_attrs:.0%})")


def _short(d: dict) -> str:
    """Compact repr of filter dict for display."""
    skip = {"limit"}
    return "  ".join(f"{k}={v}" for k, v in d.items() if k not in skip)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CafeSelect end-to-end eval")
    parser.add_argument("--labeling", action="store_true", help="Only run labeling eval")
    parser.add_argument("--search", action="store_true", help="Only run search eval")
    parser.add_argument("--db-quality", action="store_true", help="Only run DB quality eval")
    parser.add_argument("--id", type=int, help="Run a single search test case by ID")
    parser.add_argument("--category", help="Run search cases in one category")
    args = parser.parse_args()

    only_one = args.labeling or args.search or args.db_quality or args.id or args.category
    run_lab  = args.labeling  or not only_one
    run_srch = args.search    or args.id is not None or args.category or not only_one
    run_db   = args.db_quality or not only_one

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

    if run_db and not args.id and not args.category:
        print("\n" + "=" * 50)
        print("  DB Quality Eval")
        print("=" * 50)
        run_db_quality_eval()

    print("\n" + "=" * 50)
    print("  Summary")
    print("=" * 50)
    if lab_total:
        pct = 100 * lab_correct // lab_total
        print(f"Labeling:   {lab_correct}/{lab_total} attributes correct ({pct}%)")
    if srch_total:
        pct = 100 * srch_passed // srch_total
        print(f"Search:     {srch_passed}/{srch_total} cases passed ({pct}%)")
    if not lab_total and not srch_total and not args.db_quality and not only_one:
        print("No ground truth found. Add entries to eval/test_data.py to get started.")
    print()


if __name__ == "__main__":
    main()
