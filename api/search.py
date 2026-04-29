"""
CafeSelect — Supabase Search
Translates parsed filters into a Supabase query and returns matching cafes.
"""

from __future__ import annotations
import random
import re
from datetime import datetime

from openai import OpenAI
from supabase import create_client, Client

from api.config import settings

_openai = OpenAI(api_key=settings.openai_api_key)

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

EQ_FIELDS = {"neighborhood", "region"}


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
    limit = min(int(filters.pop("limit", 6)), 10)
    sort_by = filters.pop("sort_by", "rating")
    open_after = filters.pop("open_after", None)
    open_now   = filters.pop("open_now", None)

    fetch_limit = limit * 4 if (open_after or open_now) else limit * 3

    query = _supabase.table("cafes").select(RETURN_COLS)
    query = query.gte("review_count", 5)

    exclude_loud = False

    for field, value in filters.items():
        if field in BOOL_FIELDS and value is True:
            query = query.eq(field, True)
            if field == "study_friendly":
                exclude_loud = True
        elif field == "noise_level":
            if value == "quiet":
                exclude_loud = True  # most rows have null noise_level; exclude loud rather than require quiet
            else:
                query = query.eq(field, value)
        elif field == "neighborhoods":
            if isinstance(value, list) and value:
                query = query.in_("neighborhood", value)
        elif field in EQ_FIELDS:
            query = query.eq(field, value)
        elif field == "has_outlets" and value:
            query = query.gt("has_outlets", 0)

    if exclude_loud:
        query = query.or_("noise_level.neq.loud,noise_level.is.null")

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
        results = filtered

    results = random.sample(results, min(limit, len(results)))

    # Strip hours columns from response
    for r in results:
        for col in _DAY_COL:
            r.pop(col, None)

    return results


def run_embedding_search(query: str, limit: int = 6) -> list[dict]:
    """Embed the query and return cafes ranked by semantic similarity."""
    response = _openai.embeddings.create(model="text-embedding-3-small", input=query)
    vector = response.data[0].embedding

    rpc_result = _supabase.rpc(
        "match_cafes",
        {"query_embedding": vector, "match_count": limit * 3},
    ).execute()

    if not rpc_result.data:
        return []

    # Preserve similarity ranking after fetching full records
    id_order = {r["place_id"]: i for i, r in enumerate(rpc_result.data)}
    records = (
        _supabase.table("cafes")
        .select(RETURN_COLS)
        .in_("place_id", list(id_order.keys()))
        .gte("review_count", 5)
        .execute()
        .data or []
    )
    records = random.sample(records, min(limit, len(records)))

    for r in records:
        for col in _DAY_COL:
            r.pop(col, None)

    return records
