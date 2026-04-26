"""
CafeSelect — Supabase Search
Translates parsed filters into a Supabase query and returns matching cafes.
"""

from __future__ import annotations
import re
from datetime import datetime

from supabase import create_client, Client

from api.config import settings

_supabase: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_key,
)

_DAY_COL = ["hours_mon", "hours_tue", "hours_wed", "hours_thu", "hours_fri", "hours_sat", "hours_sun"]

HOURS_COLS = ",".join(_DAY_COL)

RETURN_COLS = ",".join([
    "place_id", "name", "neighborhood", "region", "address",
    "rating", "review_count", "price_level",
    "overall_vibe", "good_for_dates", "instagrammable",
    "study_friendly", "noise_level", "has_outlets",
    "open_after_5pm", "open_weekends",
    "has_matcha", "has_specialty_coffee", "has_vegan_options", "has_patio",
    "seating_capacity", "space_size", "best_time_to_visit",
    "specialty_drinks", "signature_items",
    "hero_photo_url", "google_maps_url", "website",
    "generative_summary", "review_summary",
] + _DAY_COL)

BOOL_FIELDS = {
    "study_friendly", "open_after_5pm", "open_weekends",
    "good_for_dates", "instagrammable", "has_matcha",
    "has_specialty_coffee", "has_vegan_options", "has_patio",
    "dogs_allowed", "solo_friendly", "group_friendly",
    "has_food_menu", "has_avocado_toast", "has_pastries",
    "serves_breakfast", "serves_brunch", "serves_lunch",
    "serves_dinner", "serves_dessert",
}

EQ_FIELDS = {"neighborhood", "region", "noise_level"}


def _parse_hours_range(hours_str: str | None) -> tuple[int, int] | None:
    """Parse '8:00 AM – 10:00 PM' → (800, 2200). Returns None if closed/unknown."""
    if not hours_str:
        return None
    s = hours_str.lower()
    if "closed" in s:
        return None
    if "24 hours" in s or "open 24" in s:
        return (0, 2359)

    matches = re.findall(r'(\d{1,2}):?(\d{2})?\s*(am|pm)', s)
    if len(matches) < 2:
        return None

    def to_hhmm(h_str, m_str, period):
        h = int(h_str); m = int(m_str) if m_str else 0
        if period == "pm" and h != 12:
            h += 12
        elif period == "am" and h == 12:
            h = 0
        return h * 100 + m

    open_time  = to_hhmm(*matches[0])
    close_time = to_hhmm(*matches[-1])
    return (open_time, close_time)


def _parse_closing_time(hours_str: str | None) -> int | None:
    """Parse a hours string like '8:00 AM – 10:00 PM' → 2200. Returns None if closed or unknown."""
    if not hours_str:
        return None
    s = hours_str.lower()
    if "closed" in s:
        return None
    if "24 hours" in s or "open 24" in s:
        return 2359

    # Find the closing time — last time token in the string
    matches = re.findall(r'(\d{1,2}):?(\d{2})?\s*(am|pm)', s)
    if not matches:
        return None
    h_str, m_str, period = matches[-1]
    h = int(h_str)
    m = int(m_str) if m_str else 0
    if period == "pm" and h != 12:
        h += 12
    elif period == "am" and h == 12:
        h = 0
    return h * 100 + m


def _today_hours_col() -> str:
    return _DAY_COL[datetime.now().weekday()]  # weekday(): 0=Mon, 6=Sun


def run_search(filters: dict) -> list[dict]:
    limit = min(int(filters.pop("limit", 5)), 10)
    sort_by = filters.pop("sort_by", "rating")
    open_after = filters.pop("open_after", None)
    open_now   = filters.pop("open_now", None)

    fetch_limit = limit * 4 if (open_after or open_now) else limit

    query = _supabase.table("cafes").select(RETURN_COLS)

    for field, value in filters.items():
        if field in BOOL_FIELDS and value is True:
            query = query.eq(field, True)
        elif field in EQ_FIELDS:
            query = query.eq(field, value)
        elif field == "has_outlets" and value:
            query = query.gt("has_outlets", 0)

    query = query.order(sort_by, desc=True).limit(fetch_limit)
    results = query.execute().data or []

    # Filter by hours using today's hours string
    if open_after or open_now:
        today_col = _today_hours_col()
        now_hhmm = int(datetime.now().strftime("%H%M"))
        filtered = []
        for r in results:
            hours = _parse_hours_range(r.get(today_col))
            if hours is None:
                continue
            open_time, close_time = hours
            if open_now and not (open_time <= now_hhmm <= close_time):
                continue
            if open_after and close_time < open_after:
                continue
            filtered.append(r)
        results = filtered[:limit]

    # Strip hours columns from response
    for r in results:
        for col in _DAY_COL:
            r.pop(col, None)

    return results
