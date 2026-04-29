"""
CafeSelect — Query Parser
Sends user query to Claude Haiku and returns structured filter dict.
"""

from __future__ import annotations
import json

import anthropic

from api.config import settings

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """\
You extract structured search filters from a user's cafe search query.

Available filter fields (only include fields clearly implied by the query):
- neighborhood: one of [Westwood, Culver City, Brentwood, Santa Monica, Venice, Mar Vista, Sawtelle, Palms, Century City, Pacific Palisades, Marina del Rey, Playa Vista]
- region: one of [West LA, Central LA, South LA, San Fernando Valley]
- study_friendly: true/false
- noise_level: one of [quiet, moderate, loud]
- has_outlets: 1 (has outlets) — only set if user mentions outlets/plugs/charging
- open_after: integer HHMM — closing time the user needs. Examples: "after 7pm" → 1900, "after 7:45pm" → 1945, "open late" → 2000. Only set if user mentions a specific time or "late/evening/after work". Do NOT set for "open now".
- open_now: true — only set if user says "open now" or "currently open".
- open_weekends: true — only set if user mentions weekend
- good_for_dates: true — only set if user mentions date/romantic
- instagrammable: true — only set if user mentions aesthetic/instagram/photogenic
- has_matcha: true — only set if user mentions matcha
- has_specialty_coffee: true — only set if user mentions specialty coffee/third wave
- has_vegan_options: true — only set if user mentions vegan
- has_patio: true — only set if user mentions outdoor/patio
- dogs_allowed: true — only set if user mentions dog/pet
- solo_friendly: true — only set if user mentions solo/alone
- group_friendly: true — only set if user mentions group/friends/meeting
- has_food_menu: true — only set if user mentions food/eating/meal/sandwich/lunch/snack
- has_avocado_toast: true — only set if user mentions avocado toast
- has_pastries: true — only set if user mentions pastries/croissant/baked goods
- serves_breakfast: true — only set if user mentions breakfast
- serves_brunch: true — only set if user mentions brunch
- serves_lunch: true — only set if user mentions lunch/sandwich/midday
- serves_dinner: true — only set if user mentions dinner
- serves_dessert: true — only set if user mentions dessert/cake/sweets

Also extract:
- limit: number of results requested (default 6, max 10)
- sort_by: "rating" (default) or "review_count"
- search_mode:
  - "filter" — query has specific constraints (neighborhood, hours, amenities, matcha, outlets, etc.)
  - "embedding" — query is purely about vibe/atmosphere/feeling (e.g. "chill vibe", "cozy", "aesthetic", "romantic", "feels like a library")
  - "hybrid" — query combines vibe with at least one specific constraint (e.g. "cozy cafe with matcha", "romantic spot open late")

Return ONLY valid JSON, no explanation. Example:
{"neighborhood": "Westwood", "study_friendly": true, "noise_level": "quiet", "limit": 6, "search_mode": "filter"}
"""


def parse_query(query: str) -> dict:
    """Return a dict of Supabase-ready filters extracted from the user query."""
    msg = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": query}],
        # output_format=QueryType
    )
    raw = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"limit": 5}
