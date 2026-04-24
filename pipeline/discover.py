"""
CafeSelect — Cafe Discovery
=============================
Finds new cafe place_ids in West LA neighborhoods not yet in the database.

Two modes:
  text (default) — Places Text Search, one query per neighborhood, top ~20 results.
                   Fast and cheap. Good for quick refresh / catching new openings.
  grid           — Places Nearby Search on a geographic grid. ~90% coverage.
                   Use for first-time sweep of a neighborhood.

Usage:
    python pipeline/discover.py --neighborhood westwood
    python pipeline/discover.py --neighborhood "santa monica" --mode grid
    python pipeline/discover.py --all --mode grid --out new_ids.json
    python pipeline/discover.py --list

Cost:
  text: ~$0.032/neighborhood
  grid: ~$0.29/neighborhood (3×3) — ~$0.51/neighborhood (4×4)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Env loading ───────────────────────────────────────────────────────────────

_HERE = Path(__file__).parent
_ENV_CANDIDATES = [
    _HERE.parent / ".env",
    _HERE.parent.parent / ".env",
    _HERE.parent.parent / "pre_build_validation" / ".env",
]
for _env_path in _ENV_CANDIDATES:
    if _env_path.exists():
        with open(_env_path) as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _, _v = _line.partition("=")
                _k = _k.strip(); _v = _v.strip().strip('"').strip("'")
                if _k not in os.environ:
                    os.environ[_k] = _v
        break

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
if not API_KEY:
    print("❌ GOOGLE_PLACES_API_KEY not set", file=sys.stderr)
    sys.exit(1)

BASE_URL = "https://places.googleapis.com/v1"
HEADERS = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": API_KEY,
    "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.types",
}

CAFE_TYPES = {"cafe", "coffee_shop", "bakery"}

# ── Filters ───────────────────────────────────────────────────────────────────

# Name keywords that indicate a non-cafe even if Google tagged it as cafe/bakery
EXCLUDE_NAME_KEYWORDS = [
    "pizzeria", "pizza", "sushi", "ramen", "burger", "bbq", "barbecue",
    "boba", "bubble tea", "thai", "chinese", "japanese restaurant",
    "korean restaurant", "mexican", "taqueria", "tacos",
    "grocery", "supermarket", "pharmacy", "drugstore",
    "hospital", "medical", "clinic", "museum", "hotel", "motel",
    "gas station", "convenience", "liquor", "bar & grill", "grill",
]

# Global/national chains — regional and LA-born chains (Alfred, Philz, GGET) are kept
CHAIN_BLOCKLIST = {
    "starbucks", "dunkin", "dunkin'", "peet's coffee", "peets coffee",
    "coffee bean", "the coffee bean", "coffee bean & tea leaf",
    "dutch bros", "dutch bros coffee", "tim hortons", "caribou coffee",
    "second cup", "costa coffee", "nescafe",
    "mcdonald's", "mcdonalds", "panera bread", "panera",
    "corner bakery", "corner bakery cafe", "la madeleine",
    "einstein bros", "einstein bros bagels", "noah's bagels",
    "bruegger's", "au bon pain",
    "whole foods bakery", "whole foods market", "ralphs", "ralphs fresh fare",
    "trader joe's", "target cafe", "walmart cafe", "extramile", "7-eleven",
    "insomnia cookies", "dippin dots", "jamba", "jamba juice",
    "smoothie king", "orange julius",
}

# Prefix-based chain catch (handles "Starbucks Reserve", "Dunkin' Donuts", etc.)
CHAIN_PREFIXES = ("starbucks", "dunkin")


def _is_filtered(name: str) -> bool:
    """Return True if this place should be excluded."""
    name_lower = name.lower().strip()
    if name_lower in CHAIN_BLOCKLIST:
        return True
    if any(name_lower.startswith(p) for p in CHAIN_PREFIXES):
        return True
    if any(kw in name_lower for kw in EXCLUDE_NAME_KEYWORDS):
        return True
    return False


# ── Neighborhood config ───────────────────────────────────────────────────────

NEIGHBORHOODS: dict[str, dict] = {
    "Westwood":          {"query": "cafes in Westwood Los Angeles",          "bbox": (34.055, 34.075, -118.462, -118.432), "grid": 3},
    "Brentwood":         {"query": "cafes in Brentwood Los Angeles",         "bbox": (34.040, 34.080, -118.515, -118.462), "grid": 3},
    "Santa Monica":      {"query": "cafes in Santa Monica CA",               "bbox": (34.000, 34.042, -118.520, -118.458), "grid": 4},
    "Venice":            {"query": "cafes in Venice Los Angeles",            "bbox": (33.982, 34.028, -118.482, -118.438), "grid": 4},
    "Mar Vista":         {"query": "cafes in Mar Vista Los Angeles",         "bbox": (33.998, 34.030, -118.448, -118.408), "grid": 3},
    "Culver City":       {"query": "cafes in Culver City CA",                "bbox": (33.995, 34.035, -118.415, -118.365), "grid": 3},
    "Sawtelle":          {"query": "cafes in Sawtelle Los Angeles",          "bbox": (34.018, 34.050, -118.460, -118.428), "grid": 3},
    "Palms":             {"query": "cafes in Palms Los Angeles",             "bbox": (34.005, 34.030, -118.420, -118.390), "grid": 3},
    "Century City":      {"query": "cafes in Century City Los Angeles",      "bbox": (34.048, 34.068, -118.435, -118.405), "grid": 3},
    "Pacific Palisades": {"query": "cafes in Pacific Palisades Los Angeles", "bbox": (34.030, 34.078, -118.555, -118.508), "grid": 3},
    "Marina del Rey":    {"query": "cafes in Marina del Rey Los Angeles",    "bbox": (33.972, 34.008, -118.468, -118.435), "grid": 3},
    "Playa Vista":       {"query": "cafes in Playa Vista Los Angeles",       "bbox": (33.972, 33.998, -118.445, -118.412), "grid": 3},
}

# ── HTTP session ──────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

SESSION = _make_session()

# ── Search log ────────────────────────────────────────────────────────────────

_LOG_PATH = _HERE.parent / "data" / "search_log.json"

def _append_log(entries: list[dict]) -> None:
    """Append search run entries to data/search_log.json."""
    existing = []
    if _LOG_PATH.exists():
        with open(_LOG_PATH) as f:
            existing = json.load(f)
    existing.extend(entries)
    with open(_LOG_PATH, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

# ── Existing place_ids ────────────────────────────────────────────────────────

def load_existing_ids() -> set[str]:
    repo_root = _HERE.parent.parent
    cafes_csv = repo_root / "Workspace" / "data" / "cafes_review.csv"
    if not cafes_csv.exists():
        cafes_csv = repo_root / "cafes.csv"

    if cafes_csv.exists():
        with open(cafes_csv) as f:
            ids = {row["place_id"] for row in csv.DictReader(f) if row.get("place_id")}
        print(f"  ↳ {len(ids)} existing ids from {cafes_csv.name}", file=sys.stderr)
        return ids

    db_dir = _HERE.parent / "data" / "db_records"
    if db_dir.exists():
        all_path = db_dir / "cafes.json"
        if all_path.exists():
            with open(all_path) as f:
                data = json.load(f)
            ids = {r["place_id"] for r in data if r.get("place_id")}
            print(f"  ↳ {len(ids)} existing ids from db_records/cafes.json", file=sys.stderr)
            return ids

    print("  ↳ No existing database found — all results are new", file=sys.stderr)
    return set()

# ── Text search backend ───────────────────────────────────────────────────────

def _text_search_page(query: str, page_token: str | None = None) -> tuple[list[dict], str | None]:
    url = f"{BASE_URL}/places:searchText"
    headers = {**HEADERS, "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.types,nextPageToken"}
    body: dict = {"textQuery": query, "maxResultCount": 20, "languageCode": "en"}
    if page_token:
        body["pageToken"] = page_token
    resp = SESSION.post(url, headers=headers, json=body, timeout=30)
    if resp.status_code != 200:
        print(f"  ⚠️  Text search failed (HTTP {resp.status_code}): {resp.text[:120]}", file=sys.stderr)
        return [], None
    data = resp.json()
    places = []
    for p in data.get("places", []):
        types = set(p.get("types", []))
        if not types & CAFE_TYPES:
            continue
        name = p.get("displayName", {}).get("text", "")
        if _is_filtered(name):
            continue
        places.append({"place_id": p["id"], "name": name, "address": p.get("formattedAddress", "")})
    return places, data.get("nextPageToken")


def search_text_mode(name: str, query: str, existing_ids: set[str], max_pages: int = 3) -> tuple[list[dict], int]:
    print(f"\n🔍 {name}  (\"{query}\")", file=sys.stderr)
    seen: set[str] = set()
    new_cafes: list[dict] = []
    total_found = 0
    page_token = None

    for page in range(1, max_pages + 1):
        places, page_token = _text_search_page(query, page_token)
        total_found += len(places)
        new = sum(1 for p in places if p["place_id"] not in existing_ids and p["place_id"] not in seen)
        for p in places:
            pid = p["place_id"]
            if pid not in existing_ids and pid not in seen:
                seen.add(pid)
                new_cafes.append({**p, "neighborhood": name})
        print(f"    page {page}: {len(places)} cafes, {new} new", file=sys.stderr)
        if not page_token:
            break
        time.sleep(1)

    print(f"  ✅ {len(new_cafes)} new  ({total_found} total found)", file=sys.stderr)
    return new_cafes, total_found

# ── Grid search backend ───────────────────────────────────────────────────────

def _grid_points(bbox: tuple, n: int) -> list[tuple[float, float]]:
    south, north, west, east = bbox
    if n == 1:
        return [((south + north) / 2, (west + east) / 2)]
    points = []
    for i in range(n):
        lat = south + (north - south) * i / (n - 1)
        for j in range(n):
            lon = west + (east - west) * j / (n - 1)
            points.append((lat, lon))
    return points


def _nearby_search(lat: float, lon: float, radius: float) -> list[dict]:
    url = f"{BASE_URL}/places:searchNearby"
    body = {
        "includedTypes": list(CAFE_TYPES),
        "maxResultCount": 20,
        "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": radius}},
        "languageCode": "en",
    }
    resp = SESSION.post(url, headers=HEADERS, json=body, timeout=30)
    if resp.status_code != 200:
        print(f"  ⚠️  Nearby search failed (HTTP {resp.status_code}): {resp.text[:120]}", file=sys.stderr)
        return []
    places = []
    for p in resp.json().get("places", []):
        if not set(p.get("types", [])) & CAFE_TYPES:
            continue
        name = p.get("displayName", {}).get("text", "")
        if _is_filtered(name):
            continue
        places.append({"place_id": p["id"], "name": name, "address": p.get("formattedAddress", "")})
    return places


def search_grid_mode(
    name: str, bbox: tuple, grid: int, existing_ids: set[str], radius: float = 500
) -> list[dict]:
    points = _grid_points(bbox, grid)
    print(f"\n📍 {name}  ({grid}×{grid} grid = {len(points)} points, radius={radius}m)", file=sys.stderr)

    seen: set[str] = set()
    new_cafes: list[dict] = []
    total_hits = 0

    for i, (lat, lon) in enumerate(points, 1):
        results = _nearby_search(lat, lon, radius)
        total_hits += len(results)
        new = 0
        for r in results:
            pid = r["place_id"]
            if pid in existing_ids or pid in seen:
                continue
            seen.add(pid)
            new_cafes.append({**r, "neighborhood": name})
            new += 1
        print(f"  point {i:02d}/{len(points)}  ({lat:.4f}, {lon:.4f})  → {len(results)} results, {new} new",
              file=sys.stderr)
        time.sleep(0.3)

    print(f"  ✅ {len(new_cafes)} new  |  {total_hits} total hits across grid", file=sys.stderr)
    return new_cafes, total_hits

# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover new cafe place_ids not yet in the CafeSelect database."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--neighborhood", "-n", metavar="NAME")
    group.add_argument("--all", "-a", action="store_true")
    group.add_argument("--list", "-l", action="store_true")

    parser.add_argument("--mode", choices=["text", "grid"], default="text",
                        help="Search mode: text (fast, top-20) or grid (thorough, ~90%%). Default: text")
    parser.add_argument("--grid", type=int, default=None, metavar="N",
                        help="Grid size override for grid mode (default: per-neighborhood setting)")
    parser.add_argument("--radius", type=float, default=500, metavar="M",
                        help="Search radius in meters for grid mode (default: 500)")
    parser.add_argument("--out", "-o", metavar="FILE",
                        help="Write results to JSON file instead of stdout")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be searched without calling the API")
    args = parser.parse_args()

    if args.list:
        print(f"{'Neighborhood':<22} {'Text query':<45} {'Grid'}")
        print("-" * 80)
        for name, cfg in NEIGHBORHOODS.items():
            g = args.grid or cfg["grid"]
            print(f"  {name:<20} {cfg['query']:<45} {g}×{g}")
        return

    if args.all:
        targets = list(NEIGHBORHOODS.items())
    else:
        key = args.neighborhood.lower()
        targets = [(n, cfg) for n, cfg in NEIGHBORHOODS.items() if n.lower() == key]
        if not targets:
            close = [n for n in NEIGHBORHOODS if key in n.lower()]
            msg = f"Unknown neighborhood: '{args.neighborhood}'."
            if close:
                msg += f" Did you mean: {', '.join(close)}?"
            print(f"❌ {msg}", file=sys.stderr)
            sys.exit(1)

    if args.dry_run:
        print(f"Dry run ({args.mode} mode) — would search:", file=sys.stderr)
        for name, cfg in targets:
            if args.mode == "grid":
                g = args.grid or cfg["grid"]
                print(f"  {name}: {g}×{g} grid, radius={args.radius}m", file=sys.stderr)
            else:
                print(f"  {name}: \"{cfg['query']}\"", file=sys.stderr)
        return

    print(f"\n{'='*55}", file=sys.stderr)
    print(f"  CafeSelect — Discover ({args.mode} mode)", file=sys.stderr)
    print(f"  Neighborhoods: {', '.join(n for n, _ in targets)}", file=sys.stderr)
    print(f"{'='*55}", file=sys.stderr)

    existing_ids = load_existing_ids()
    all_new: list[dict] = []
    log_entries: list[dict] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    for name, cfg in targets:
        if args.mode == "grid":
            grid = args.grid or cfg["grid"]
            new, total_found = search_grid_mode(name, cfg["bbox"], grid, existing_ids, args.radius)
        else:
            new, total_found = search_text_mode(name, cfg["query"], existing_ids)
        all_new.extend(new)
        log_entries.append({
            "ts": ts,
            "mode": args.mode,
            "neighborhood": name,
            "found": total_found,
            "new": len(new),
            "already_in_db": total_found - len(new),
        })

    if not args.dry_run:
        _append_log(log_entries)

    print(f"\n{'='*55}", file=sys.stderr)
    print(f"  Total new cafes: {len(all_new)}", file=sys.stderr)
    print(f"{'='*55}\n", file=sys.stderr)

    output = json.dumps(all_new, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(output)
        print(f"✅ Written to {args.out}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
