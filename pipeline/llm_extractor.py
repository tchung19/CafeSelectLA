"""
CafeSelect — LLM Attribute Extractor (Claude Haiku 4.5)
========================================================
Extracts structured cafe attributes from Google reviews + AI summaries.

Ingests: raw reviews + generativeSummary + reviewSummary + neighborhoodSummary.
Returns: validated Pydantic model covering attribute_schema.md sections 5–8.

Uses:
  - client.messages.parse()  → schema-enforced JSON output
  - cache_control on system  → ~90% token discount after first cafe
"""

from __future__ import annotations

from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from config import settings, require

require("ANTHROPIC_API_KEY", settings.anthropic_api_key)

MODEL = "claude-haiku-4-5"
_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


# ── Output schema ─────────────────────────────────────────────────────────────

NoiseLevel       = Literal["quiet", "moderate", "loud", "varies", "unknown"]
SeatingComfort   = Literal["comfortable", "average", "uncomfortable", "unknown"]
SpaceSize        = Literal["tiny", "small", "medium", "spacious", "unknown"]
StaffFriendliness = Literal["excellent", "good", "average", "poor", "unknown"]
PricePerception  = Literal["great_value", "fair", "pricey", "overpriced", "unknown"]


class CafeAttributes(BaseModel):
    """LLM-extracted cafe attributes (attribute_schema.md sections 5–8, source=L)."""

    # §5 Work & Study
    has_outlets: int = Field(ge=0, le=5, description="0=no outlets/never mentioned … 5=abundant")
    outlet_confidence: float = Field(ge=0, le=1)
    outlet_mentions: int = Field(ge=0)
    wifi_quality: int = Field(ge=0, le=5)
    wifi_confidence: float = Field(ge=0, le=1)
    study_friendly: bool
    study_confidence: float = Field(ge=0, le=1)
    laptop_policy: Optional[str] = Field(default=None)
    noise_level: NoiseLevel
    noise_notes: Optional[str] = Field(default=None)
    solo_friendly: bool
    solo_confidence: float = Field(ge=0, le=1)

    # §6 Space & Physical (L-sourced subset)
    seating_comfort: SeatingComfort
    seating_comfort_notes: Optional[str] = Field(default=None)
    space_size: SpaceSize

    # §7 Vibe & Social
    overall_vibe: list[str] = Field(description="exactly 3 tags — the most distinctive vibes from reviews, free-form, lowercase")
    good_for_dates: bool
    date_confidence: float = Field(ge=0, le=1)
    group_friendly: bool
    group_confidence: float = Field(ge=0, le=1)
    best_time_to_visit: Optional[str] = Field(default=None)
    staff_friendliness: StaffFriendliness
    staff_notes: Optional[str] = Field(default=None)
    price_perception: PricePerception
    price_notes: Optional[str] = Field(default=None)

    # §8 Food & Drink (L-sourced subset)
    has_matcha: bool
    has_avocado_toast: bool
    has_specialty_coffee: bool
    has_food_menu: bool
    specialty_drinks: list[str]
    signature_items: list[str]
    has_vegan_options: bool
    has_pastries: bool


# ── System prompt (stable = cache-friendly) ───────────────────────────────────

SYSTEM_PROMPT = """You are CafeSelect's attribute-extraction assistant. Your job is to read everything a user provides about a single cafe — Google review text, Google-generated overview/description, Google's condensed review summary, and the neighborhood summary — and return a strict JSON object describing that cafe's attributes.

You are extracting structured data that will feed a consumer-facing cafe search product. Accuracy and calibration matter more than optimism. Never invent details. When the provided text says nothing about an attribute, choose the conservative default (see per-field rules) and set the related confidence low.

# General rules

1. **Ground every claim in the provided text.** If a reviewer doesn't mention it and no summary covers it, you do not know it. Do not infer from the cafe's name, address, or typical-cafe expectations.
2. **Confidence scores** (all `*_confidence` fields, 0.0–1.0):
   - 0.0–0.2: not mentioned at all, or only the faintest indirect signal.
   - 0.3–0.5: one indirect or ambiguous mention.
   - 0.6–0.8: one clear mention or multiple consistent signals.
   - 0.9–1.0: multiple reviews + a Google summary agree explicitly.
3. **Booleans default to `false`** unless the text gives clear evidence for `true`.
4. **Enums that include `unknown`**: prefer `unknown` over a wrong guess when there is genuinely no signal.
5. **Optional string fields** (`*_notes`, `laptop_policy`, `best_time_to_visit`): return `null` when nothing specific is worth saying.
6. **Lists** (`overall_vibe`, `specialty_drinks`, `signature_items`): return `[]` rather than inventing filler. Deduplicate. Lowercase.
7. **Weight Google's summaries higher than any single review** — they were synthesized from ALL reviews.
8. **Sentiment caveat**: "too loud to work" is evidence the place IS loud, not that it isn't study-friendly for everyone.

# Field-by-field extraction rules

## Work & Study (§5)
- `has_outlets` (int 0–5): 0=zero signal. 1-2=vague/scarce. 3="there are outlets". 4="plenty". 5="every seat has an outlet".
- `outlet_mentions`: literal count of raw reviews mentioning outlets/plugs/charging (summaries don't count).
- `wifi_quality` (int 0–5): 0=no wifi/not mentioned. 3="has wifi" no complaints. 1-2=reliability complaints. 4–5=explicitly fast/reliable.
- `study_friendly`: true only if overall picture supports 2+ hours laptop work.
- `noise_level`: "varies" when reviews describe different conditions at different times.
- `solo_friendly`: true if a solo person could comfortably sit, read, work, or people-watch.

## Space & Physical (§6, L-subset)
- `seating_comfort`: "comfortable" requires positive mentions. "uncomfortable" requires explicit complaints. Default "average".
- `space_size`: be conservative. "spacious" requires explicit signal.

## Vibe & Social (§7)
- `overall_vibe`: exactly 3 tags. Free-form, lowercase. Pick the most *distinctive* vibes that set this cafe apart — not generic descriptors that apply to every cafe (avoid: "cozy", "casual", "chill" unless they are genuinely the defining quality). Think about what a friend would say to describe this specific place: "it's that Korean specialty coffee spot", "very Japanese minimal", "feels like a living room", "Aussie brunch chain energy".
- `good_for_dates`: intimate + not too loud + nice enough for a first/second date.
- `staff_friendliness`: "excellent" requires multiple positive mentions. "poor" requires explicit complaints. Default "average".
- `price_perception`: default "fair" when silent.

## Food & Drink (§8, L-subset)
- `has_matcha`, `has_avocado_toast`: only true if explicitly mentioned.
- `has_specialty_coffee`: true for pour-over, single-origin, latte art, house-roasted. NOT just for lattes.
- `has_food_menu`: true only for real cooked food beyond pastries.
- `specialty_drinks`: named non-standard drinks only. Lowercase, deduplicate.
- `signature_items`: items praised by 2+ reviewers.
- `has_pastries`: true if baked goods are mentioned.

# Output
Return exactly one JSON object matching the schema. No prose, no code fences."""


# ── Extraction function ───────────────────────────────────────────────────────

def _build_user_prompt(
    cafe_name: str,
    reviews: list[dict],
    gen_overview: str,
    gen_description: str,
    review_summary: str,
    neighborhood_summary: str,
) -> str:
    parts: list[str] = [f"# Cafe: {cafe_name}\n"]
    parts.append("## Google Generative Summary — Overview\n")
    parts.append(gen_overview.strip() if gen_overview else "_not available_")
    parts.append("\n\n## Google Generative Summary — Description\n")
    parts.append(gen_description.strip() if gen_description else "_not available_")
    parts.append("\n\n## Google Review Summary (condensed from ALL reviews)\n")
    parts.append(review_summary.strip() if review_summary else "_not available_")
    parts.append("\n\n## Google Neighborhood Summary\n")
    parts.append(neighborhood_summary.strip() if neighborhood_summary else "_not available_")
    parts.append(f"\n\n## Raw reviews ({len(reviews)} returned by the API)\n")
    if not reviews:
        parts.append("_no reviews returned_")
    else:
        for i, r in enumerate(reviews, 1):
            author = r.get("authorAttribution", {}).get("displayName", "Anonymous")
            rating = r.get("rating", "?")
            when = r.get("relativePublishTimeDescription", "unknown time")
            text = r.get("text", {}).get("text") or r.get("originalText", {}).get("text", "")
            parts.append(f"\n### Review {i} — {author}, {rating}/5, {when}\n{text.strip() or '(no text)'}\n")
    parts.append("\n\nExtract the attributes per the schema. Return the JSON object only.")
    return "".join(parts)


def extract_attributes(
    cafe_name: str,
    reviews: list[dict],
    gen_overview: str = "",
    gen_description: str = "",
    review_summary: str = "",
    neighborhood_summary: str = "",
) -> dict:
    """
    Extract structured cafe attributes via Claude Haiku 4.5.

    Returns:
        {
            "attributes": dict (CafeAttributes fields),
            "usage": token usage including cache stats,
            "model": model name,
        }
    """
    user_prompt = _build_user_prompt(
        cafe_name=cafe_name,
        reviews=reviews,
        gen_overview=gen_overview,
        gen_description=gen_description,
        review_summary=review_summary,
        neighborhood_summary=neighborhood_summary,
    )

    response = _client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_prompt}],
        output_format=CafeAttributes,
    )

    return {
        "attributes": response.parsed_output.model_dump(),
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        },
        "model": MODEL,
    }
