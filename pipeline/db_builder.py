"""
CafeSelect — DB Record Builder
================================
Merges each cafe's three JSON files into a single record matching attribute_schema.md:
  - details.json          (Google Places API — identity, hours, structured attrs)
  - llm_attributes.json   (Claude Haiku — text-latent attrs: sentiment, vibe, noise)
  - v2_aggregate.json     (Vision pipeline — physical-space attrs: seating, lighting)

Output:
  <output-dir>/
    cafes.json          ← array of all records
    <folder>.json       ← one file per cafe

Usage:
    python pipeline/db_builder.py --data-dir data/cafes/ --out-dir data/db_records/
    python pipeline/db_builder.py --data-dir data/cafes/ --out-dir data/db_records/ --cafe 01_Upside_Down
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import datetime
from pathlib import Path

from regions import extract_neighborhood, region_from_neighborhood


# ── "Truly instagrammable" heuristic ─────────────────────────────────────────

IG_KILLER_TAGS = {"upscale", "traditional", "conventional", "chain-style", "corporate"}
IG_DISTINCTIVE_TAGS = {
    "aesthetic", "minimalist", "industrial", "artsy", "zen", "earthy",
    "wellness", "bohemian", "plant-filled", "photogenic", "community-centered",
}


def compute_truly_instagrammable(vibe: list[str] | None, decor: list[str] | None) -> bool:
    tags = {str(t).lower() for t in (vibe or [])} | {str(t).lower() for t in (decor or [])}
    if tags & IG_KILLER_TAGS:
        return False
    return bool(tags & IG_DISTINCTIVE_TAGS)


# ── "Good for dates" heuristic ────────────────────────────────────────────────

DATE_KILLER_TAGS     = {"lively", "bustling"}
DATE_LOUD_NOISE      = {"loud"}


def compute_good_for_dates(
    vibe: list[str] | None, decor: list[str] | None, noise_level: str | None
) -> bool:
    tags = {str(t).lower() for t in (vibe or [])} | {str(t).lower() for t in (decor or [])}
    if tags & IG_KILLER_TAGS:
        return False
    if tags & DATE_KILLER_TAGS:
        return False
    if noise_level and noise_level.lower() in DATE_LOUD_NOISE:
        return False
    return len(tags & IG_DISTINCTIVE_TAGS) >= 2


def compute_date_score(
    vibe: list[str] | None, decor: list[str] | None, noise_level: str | None
) -> int:
    tags = {str(t).lower() for t in (vibe or [])} | {str(t).lower() for t in (decor or [])}
    score = 0
    if tags & IG_KILLER_TAGS:
        score -= 5
    score += len(tags & IG_DISTINCTIVE_TAGS)
    noise = (noise_level or "").lower()
    if noise == "quiet":
        score += 2
    elif noise == "moderate":
        score += 1
    elif noise == "loud":
        score -= 3
    if "lively" in tags:
        score -= 2
    return score


# ── Field helpers ─────────────────────────────────────────────────────────────

def _hours_by_weekday(details: dict) -> dict[str, str | None]:
    wd = details.get("regularOpeningHours", {}).get("weekdayDescriptions", [])
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    out = {d: None for d in days}
    for i, desc in enumerate(wd[:7]):
        hours_part = desc.split(":", 1)[1].strip() if ":" in desc else desc
        out[days[i]] = hours_part
    return out


def _derive_hours_flags(details: dict) -> dict:
    periods = details.get("regularOpeningHours", {}).get("periods", []) or []
    open_after_5 = False
    open_weekend  = False
    for p in periods:
        close = p.get("close")
        op    = p.get("open")
        if close:
            hour = close.get("hour", 0)
            if hour >= 17 or (hour == 0 and close.get("minute", 0) == 0):
                open_after_5 = True
        if op and op.get("day") in (0, 6):
            open_weekend = True
    return {"open_after_5pm": open_after_5, "open_weekends": open_weekend}


def _parking_flags(details: dict) -> dict:
    po = details.get("parkingOptions", {}) or {}
    return {
        "parking_free":   any(po.get(k) for k in ("freeParkingLot", "freeStreetParking", "freeGarageParking")) or None,
        "parking_paid":   any(po.get(k) for k in ("paidParkingLot", "paidStreetParking", "paidGarageParking")) or None,
        "parking_street": po.get("freeStreetParking") or po.get("paidStreetParking") or None,
        "parking_garage": po.get("freeGarageParking") or po.get("paidGarageParking") or None,
    }


def _photo_resource_names(details: dict) -> list[str]:
    return [p.get("name") for p in (details.get("photos") or []) if p.get("name")]


def _merge_bool_or(*values) -> bool | None:
    seen = [v for v in values if v is not None]
    if not seen:
        return None
    return any(bool(v) for v in seen)


def _merge_lists(*lists) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for lst in lists:
        for item in (lst or []):
            key = str(item).lower().strip()
            if key and key not in seen:
                seen.add(key)
                out.append(key)
    return out


def _normalize_space_size(llm_val: str | None, vision_capacity: str | None) -> str | None:
    if llm_val and llm_val != "unknown":
        return llm_val
    if vision_capacity:
        v = vision_capacity.lower()
        if "small" in v:
            return "small"
        if "medium" in v:
            return "medium"
        if "large" in v:
            return "spacious"
    return None


def _enum_or_null(v: str | None) -> str | None:
    if not v or v == "unknown":
        return None
    return v


# ── Main record builder ───────────────────────────────────────────────────────

def build_record(details: dict, llm_wrapper: dict | None, vision_wrapper: dict | None) -> dict:
    """Merge three source dicts into one DB record per attribute_schema.md."""
    llm    = (llm_wrapper    or {}).get("attributes", {}) or {}
    vision = (vision_wrapper or {}).get("analysis",   {}) or {}

    hours       = _hours_by_weekday(details)
    hours_flags = _derive_hours_flags(details)
    parking     = _parking_flags(details)
    neighborhood = extract_neighborhood(details)
    photos      = _photo_resource_names(details)

    record: dict = {
        # §1 Identity & Location
        "place_id":        details.get("id"),
        "name":            details.get("displayName", {}).get("text"),
        "address":         details.get("formattedAddress"),
        "neighborhood":    neighborhood,
        "region":          region_from_neighborhood(neighborhood),
        "latitude":        details.get("location", {}).get("latitude"),
        "longitude":       details.get("location", {}).get("longitude"),
        "google_maps_url": details.get("googleMapsUri"),
        "website":         details.get("websiteUri"),
        "phone":           details.get("nationalPhoneNumber"),
        "primary_type":    details.get("primaryType"),

        # §2 Hours & Status
        "business_status": details.get("businessStatus"),
        "hours_mon":       hours["mon"],
        "hours_tue":       hours["tue"],
        "hours_wed":       hours["wed"],
        "hours_thu":       hours["thu"],
        "hours_fri":       hours["fri"],
        "hours_sat":       hours["sat"],
        "hours_sun":       hours["sun"],
        "open_after_5pm":  hours_flags["open_after_5pm"],
        "open_weekends":   hours_flags["open_weekends"],

        # §3 Ratings & Reviews
        "rating":              details.get("rating"),
        "review_count":        details.get("userRatingCount"),
        "price_level":         details.get("priceLevel"),
        "editorial_summary":   details.get("editorialSummary", {}).get("text"),
        "review_summary":      (details.get("reviewSummary", {}) or {}).get("text", {}).get("text"),
        "generative_summary":  (details.get("generativeSummary", {}) or {}).get("overview", {}).get("text"),

        # §4 Google Structured
        "outdoor_seating":    details.get("outdoorSeating"),
        "dine_in":            details.get("dineIn"),
        "takeout":            details.get("takeout"),
        "delivery":           details.get("delivery"),
        "reservable":         details.get("reservable"),
        "dogs_allowed":       details.get("allowsDogs"),
        "good_for_children":  details.get("goodForChildren"),
        "restroom":           details.get("restroom"),
        "live_music":         details.get("liveMusic"),
        "serves_coffee":      details.get("servesCoffee"),
        "serves_breakfast":   details.get("servesBreakfast"),
        "serves_brunch":      details.get("servesBrunch"),
        "serves_lunch":       details.get("servesLunch"),
        "serves_dinner":      details.get("servesDinner"),
        "serves_dessert":     details.get("servesDessert"),
        "serves_vegetarian":  details.get("servesVegetarianFood"),
        "parking_free":       parking["parking_free"],
        "parking_paid":       parking["parking_paid"],
        "parking_street":     parking["parking_street"],
        "parking_garage":     parking["parking_garage"],

        # §5 Work & Study (L-sourced)
        "has_outlets":       llm.get("has_outlets"),
        "outlet_confidence": llm.get("outlet_confidence"),
        "outlet_mentions":   llm.get("outlet_mentions"),
        "wifi_quality":      llm.get("wifi_quality"),
        "wifi_confidence":   llm.get("wifi_confidence"),
        "study_friendly":    _merge_bool_or(llm.get("study_friendly"), vision.get("laptop_friendly")),
        "study_confidence":  llm.get("study_confidence"),
        "laptop_policy":     llm.get("laptop_policy"),
        "noise_level":       _enum_or_null(llm.get("noise_level")),
        "noise_notes":       llm.get("noise_notes"),
        "solo_friendly":     llm.get("solo_friendly"),
        "solo_confidence":   llm.get("solo_confidence"),

        # §6 Space & Physical (V-heavy, L for comfort/size)
        "seating_types":           vision.get("seating_type") or [],
        "seating_capacity":        vision.get("seating_capacity"),
        "seating_comfort":         _enum_or_null(llm.get("seating_comfort")),
        "seating_comfort_notes":   llm.get("seating_comfort_notes"),
        "space_size":              _normalize_space_size(llm.get("space_size"), vision.get("seating_capacity")),
        "lighting":                vision.get("lighting"),
        "decor_style":             vision.get("decor_style") or [],
        "cleanliness":             vision.get("cleanliness"),
        "has_patio":               _merge_bool_or(vision.get("has_patio"), details.get("outdoorSeating")),
        "counter_service":         vision.get("counter_service"),
        "has_display_case":        vision.get("has_display_case"),

        # §7 Vibe & Social
        "overall_vibe":       (llm.get("overall_vibe") or [])[:3],
        "instagrammable":     None,  # computed below
        "instagrammable_vision_raw": vision.get("instagrammable"),
        "instagram_confidence": (
            {"high": 0.9, "medium": 0.6, "low": 0.3}.get(
                (vision.get("instagram_confidence") or "").lower()
            ) if vision.get("instagram_confidence") else None
        ),
        "good_for_dates":     llm.get("good_for_dates"),
        "date_confidence":    llm.get("date_confidence"),
        "group_friendly":     llm.get("group_friendly"),
        "group_confidence":   llm.get("group_confidence"),
        "best_time_to_visit": llm.get("best_time_to_visit"),
        "staff_friendliness": _enum_or_null(llm.get("staff_friendliness")),
        "staff_notes":        llm.get("staff_notes"),
        "price_perception":   _enum_or_null(llm.get("price_perception")),
        "price_notes":        llm.get("price_notes"),

        # §8 Food & Drink
        "has_matcha": _merge_bool_or(
            llm.get("has_matcha"),
            (any("matcha" in str(x).lower() for x in (vision.get("drink_types_visible") or []))) or None,
        ),
        "has_avocado_toast": _merge_bool_or(
            llm.get("has_avocado_toast"),
            (any("avocado" in str(x).lower() for x in (vision.get("food_visible") or []))) or None,
        ),
        "has_specialty_coffee": llm.get("has_specialty_coffee"),
        "has_food_menu": _merge_bool_or(
            llm.get("has_food_menu"),
            bool(vision.get("food_visible")) if vision.get("food_visible") else None,
        ),
        "specialty_drinks":  llm.get("specialty_drinks") or [],
        "signature_items":   llm.get("signature_items") or [],
        "food_visible":      vision.get("food_visible") or [],
        "drinks_visible":    vision.get("drink_types_visible") or [],
        "has_vegan_options": _merge_bool_or(llm.get("has_vegan_options"), details.get("servesVegetarianFood")),
        "has_pastries":      _merge_bool_or(llm.get("has_pastries"), vision.get("has_display_case")),

        # §9 Photos
        "photo_urls":     photos,
        "hero_photo_url": photos[0] if photos else None,
        "photo_types":    vision.get("photo_types") or [],

        # §10 AI-Generated Content (separate pipeline step)
        "ai_summary":    None,
        "top_attributes": None,
        "embedding":     None,
    }

    # Derived fields (require overall_vibe + decor_style to be set)
    record["instagrammable"] = compute_truly_instagrammable(record["overall_vibe"], record["decor_style"])
    record["good_for_dates_llm_raw"] = record["good_for_dates"]
    record["good_for_dates"] = compute_good_for_dates(record["overall_vibe"], record["decor_style"], record["noise_level"])
    record["date_score"] = compute_date_score(record["overall_vibe"], record["decor_style"], record["noise_level"])

    return record


# ── Completeness reporting ────────────────────────────────────────────────────

_SECTIONS: dict[str, list[str]] = {
    "Identity & Location": ["place_id", "name", "address", "neighborhood", "region",
                            "latitude", "longitude", "google_maps_url", "website", "phone", "primary_type"],
    "Hours & Status":      ["business_status", "hours_mon", "hours_tue", "hours_wed", "hours_thu",
                            "hours_fri", "hours_sat", "hours_sun", "open_after_5pm", "open_weekends"],
    "Ratings & Reviews":   ["rating", "review_count", "price_level", "editorial_summary",
                            "review_summary", "generative_summary"],
    "Google Structured":   ["outdoor_seating", "dine_in", "takeout", "delivery", "reservable",
                            "dogs_allowed", "good_for_children", "restroom", "live_music",
                            "serves_coffee", "serves_breakfast", "serves_brunch", "serves_lunch",
                            "serves_dinner", "serves_dessert", "serves_vegetarian",
                            "parking_free", "parking_paid", "parking_street", "parking_garage"],
    "Work & Study":        ["has_outlets", "outlet_confidence", "outlet_mentions", "wifi_quality",
                            "wifi_confidence", "study_friendly", "study_confidence", "laptop_policy",
                            "noise_level", "noise_notes", "solo_friendly", "solo_confidence"],
    "Space & Physical":    ["seating_types", "seating_capacity", "seating_comfort", "seating_comfort_notes",
                            "space_size", "lighting", "decor_style", "cleanliness",
                            "has_patio", "counter_service", "has_display_case"],
    "Vibe & Social":       ["overall_vibe", "instagrammable", "instagram_confidence", "good_for_dates",
                            "date_confidence", "group_friendly", "group_confidence", "best_time_to_visit",
                            "staff_friendliness", "staff_notes", "price_perception", "price_notes"],
    "Food & Drink":        ["has_matcha", "has_avocado_toast", "has_specialty_coffee", "has_food_menu",
                            "specialty_drinks", "signature_items", "food_visible", "drinks_visible",
                            "has_vegan_options", "has_pastries"],
    "Photos":              ["photo_urls", "hero_photo_url", "photo_types"],
    "AI Content":          ["ai_summary", "top_attributes", "embedding"],
}


def _is_filled(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, str, dict)) and not v:
        return False
    return True


def completeness(rec: dict) -> dict[str, str]:
    return {
        section: f"{sum(_is_filled(rec.get(f)) for f in fields)}/{len(fields)}"
        for section, fields in _SECTIONS.items()
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _resolve_vision(cafe_dir: Path) -> dict | None:
    """Accept v2_aggregate.json (new) or vision_analysis.json (legacy)."""
    for name in ("v2_aggregate.json", "vision_analysis.json"):
        p = cafe_dir / name
        if p.exists():
            with open(p) as f:
                return json.load(f)
    return None


def run(data_dir: str, out_dir: str, cafe_filter: str | None = None) -> None:
    root = Path(data_dir)
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    cafe_dirs = sorted(
        Path(d) for d in glob.glob(str(root / "*"))
        if os.path.isdir(d)
    )
    if cafe_filter:
        key = cafe_filter.lower()
        cafe_dirs = [d for d in cafe_dirs if key in d.name.lower()]

    if not cafe_dirs:
        print(f"❌ No cafe folders found in {data_dir}")
        return

    print(f"\n{'=' * 60}")
    print(f"  Build DB records — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  {len(cafe_dirs)} cafes  →  {out_dir}")
    print(f"{'=' * 60}\n")

    records: list[dict] = []

    for cafe_dir in cafe_dirs:
        folder = cafe_dir.name
        details = _load_json(cafe_dir / "details.json")
        if not details:
            print(f"  [{folder}] ❌ missing details.json, skipping")
            continue

        llm_wrapper    = _load_json(cafe_dir / "llm_attributes.json")
        vision_wrapper = _resolve_vision(cafe_dir)

        rec = build_record(details, llm_wrapper, vision_wrapper)
        records.append(rec)

        comp = completeness(rec)
        comp_str = "  ".join(f"{k}={v}" for k, v in comp.items())
        print(f"  [{folder}] {rec['name']}")
        print(f"    {comp_str}")

    all_path = output / "cafes.json"
    with open(all_path, "w") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    if records:
        tot: dict[str, list[int]] = {}
        for r in records:
            for section, ratio in completeness(r).items():
                filled, total = ratio.split("/")
                tot.setdefault(section, [0, 0])
                tot[section][0] += int(filled)
                tot[section][1] += int(total)
        print(f"\n  Aggregate completeness across {len(records)} cafes:")
        for section, (filled, total) in tot.items():
            pct = 100 * filled / total if total else 0
            print(f"    {section:<25} {filled}/{total}  ({pct:.0f}%)")

    print(f"\n✅ {len(records)} records → {out_dir}/cafes.json\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build DB records by merging details.json + llm_attributes.json + vision JSON."
    )
    parser.add_argument("--data-dir", "-d", required=True, metavar="DIR",
                        help="Root directory containing cafe subdirectories")
    parser.add_argument("--out-dir", "-o", required=True, metavar="DIR",
                        help="Output directory for db_records")
    parser.add_argument("--cafe", metavar="NAME",
                        help="Only process cafes whose folder name contains NAME")
    args = parser.parse_args()

    run(data_dir=args.data_dir, out_dir=args.out_dir, cafe_filter=args.cafe)


if __name__ == "__main__":
    main()
