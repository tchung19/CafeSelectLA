"""
CafeSelect — Google Places API Client
=======================================
Clean API client for the Places API (New).
Handles: text search, place details, photo download.

No file I/O, no markdown, no LLM — pure API calls.
"""

import os
import re
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import settings, require

require("GOOGLE_PLACES_API_KEY", settings.google_places_api_key)

BASE_URL = "https://places.googleapis.com/v1"
HEADERS = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": settings.google_places_api_key,
}

# ── Session ───────────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

SESSION = _make_session()

# ── Field masks ───────────────────────────────────────────────────────────────

DETAILS_FIELD_MASK = ",".join([
    "id", "displayName", "formattedAddress", "addressComponents",
    "location", "rating", "userRatingCount", "priceLevel",
    "websiteUri", "nationalPhoneNumber", "internationalPhoneNumber",
    "regularOpeningHours", "reviews", "photos",
    "editorialSummary", "generativeSummary", "reviewSummary", "neighborhoodSummary",
    "types", "primaryType", "primaryTypeDisplayName",
    "goodForChildren", "allowsDogs", "outdoorSeating",
    "servesBreakfast", "servesBrunch", "servesLunch", "servesDinner",
    "servesCoffee", "servesDessert", "servesVegetarianFood",
    "takeout", "dineIn", "delivery", "reservable", "restroom",
    "liveMusic", "accessibilityOptions", "parkingOptions", "paymentOptions",
    "googleMapsUri", "businessStatus",
])

# ── Helpers ───────────────────────────────────────────────────────────────────

def sanitize_name(name: str) -> str:
    clean = re.sub(r"[^\w\s-]", "", name)
    clean = re.sub(r"\s+", "_", clean.strip())
    return clean


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

# ── API calls ─────────────────────────────────────────────────────────────────

def search_text(
    query: str,
    max_results: int = 20,
    page_token: str | None = None,
) -> dict:
    """
    Places Text Search (New). Returns the raw API response dict.
    Response contains: places[], nextPageToken (if more results exist).
    """
    url = f"{BASE_URL}/places:searchText"
    headers = {
        **HEADERS,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.types",
    }
    body: dict = {
        "textQuery": query,
        "maxResultCount": min(max_results, 20),
        "languageCode": "en",
    }
    if page_token:
        body["pageToken"] = page_token

    resp = SESSION.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_place_details(place_id: str) -> dict:
    """
    Fetch full place details for a single place_id.
    Returns the raw API response dict.
    """
    url = f"{BASE_URL}/places/{place_id}"
    headers = {**HEADERS, "X-Goog-FieldMask": DETAILS_FIELD_MASK}

    resp = SESSION.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_photo(photo_resource_name: str, save_path: str | Path, max_width: int = 1600) -> Path:
    """
    Download a photo by its resource name and save to disk.
    Returns the path written.
    """
    url = f"{BASE_URL}/{photo_resource_name}/media"
    params = {"maxWidthPx": max_width, "key": settings.google_places_api_key}

    resp = SESSION.get(url, params=params, timeout=30, stream=True)
    resp.raise_for_status()

    path = Path(save_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return path


def fetch_and_save_cafe(
    place_id: str,
    output_dir: str | Path,
    folder_prefix: str = "",
    max_photos: int = 10,
) -> tuple[str, dict]:
    """
    Fetch details + photos for one cafe and save to disk.
    Returns (folder_name, details_dict).
    """
    import json

    details = get_place_details(place_id)
    display_name = details.get("displayName", {}).get("text", place_id)
    folder_name = f"{folder_prefix}{sanitize_name(display_name)}" if folder_prefix else sanitize_name(display_name)
    cafe_dir = ensure_dir(Path(output_dir) / folder_name)

    # details.json
    with open(cafe_dir / "details.json", "w") as f:
        json.dump(details, f, indent=2, ensure_ascii=False)

    # photos/
    photos = details.get("photos") or []
    if photos:
        photos_dir = ensure_dir(cafe_dir / "photos")
        for i, photo in enumerate(photos[:max_photos], 1):
            resource = photo.get("name")
            if not resource:
                continue
            save_path = photos_dir / f"photo_{i}.jpg"
            if save_path.exists():
                continue
            try:
                fetch_photo(resource, save_path)
            except Exception as e:
                print(f"  ⚠️  photo {i} failed: {e}")
            time.sleep(0.3)

    return folder_name, details
