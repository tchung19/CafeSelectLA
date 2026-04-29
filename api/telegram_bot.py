"""
CafeSelect — Telegram Bot Handler
Receives webhook updates from Telegram, runs a search, and replies.
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx

from api.config import settings
from api.query_parser import parse_query
from api.search import run_search, run_embedding_search, _DAY_COL

_TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_token}"

_DAY_COL_TODAY = _DAY_COL[datetime.now().weekday()]

_ATTRIBUTE_CHIPS: list[tuple[str, str]] = [
    ("study_friendly",      "📚 Study-friendly"),
    ("has_outlets",         "🔌 Outlets"),
    ("has_matcha",          "🍵 Matcha"),
    ("has_specialty_coffee","☕ Specialty coffee"),
    ("has_patio",           "🌿 Patio"),
    ("good_for_dates",      "💛 Date-friendly"),
    ("instagrammable",      "📸 Aesthetic"),
    ("has_vegan_options",   "🌱 Vegan options"),
    ("has_pastries",        "🥐 Pastries"),
    ("dogs_allowed",        "🐾 Dog-friendly"),
]

_WELCOME = (
    "👋 <b>Welcome to CafeSelect!</b>\n\n"
    "Describe what you're looking for and I'll find cafes that match.\n\n"
    "<b>Try something like:</b>\n"
    "• quiet study cafe in westwood with outlets\n"
    "• matcha spots in santa monica open late\n"
    "• cozy date night cafe in venice\n"
    "• outdoor patio cafe in culver city\n\n"
    "I cover West LA — Westwood, Santa Monica, Venice, Culver City, Brentwood, Sawtelle, and more."
)


def _parse_closing_time(hours_str: str | None) -> str | None:
    """Return a human-readable closing time like '9PM', or None."""
    if not hours_str:
        return None
    s = hours_str.lower()
    if "closed" in s:
        return None
    if "24 hours" in s or "open 24" in s:
        return "midnight"

    matches = re.findall(r'(\d{1,2}):?(\d{2})?\s*(am|pm)', s)
    if not matches:
        return None
    h_str, m_str, period = matches[-1]
    h = int(h_str)
    m = int(m_str) if m_str else 0
    if m:
        return f"{h}:{m:02d}{period.upper()}"
    return f"{h}{period.upper()}"


def _chips(cafe: dict) -> str:
    """Return up to 3 attribute chips as a single line."""
    parts = []
    if cafe.get("noise_level") == "quiet":
        parts.append("🤫 Quiet")
    for field, label in _ATTRIBUTE_CHIPS:
        if len(parts) >= 3:
            break
        val = cafe.get(field)
        if val and val is not False and val != 0:
            parts.append(label)
    return " · ".join(parts)


def _format_cafe(cafe: dict) -> str:
    today_col = _DAY_COL[datetime.now().weekday()]
    close = _parse_closing_time(cafe.get(today_col))

    rating = cafe.get("rating")
    review_count = cafe.get("review_count")
    rating_str = f"⭐ {rating}" if rating else ""
    if rating_str and review_count:
        rating_str += f" ({review_count:,})"

    location = cafe.get("neighborhood") or cafe.get("region") or ""
    meta = " · ".join(filter(None, [location, rating_str]))

    chips = _chips(cafe)
    hours_line = f"🕘 Closes {close}" if close else ""
    maps_url = cafe.get("google_maps_url") or ""
    maps_line = f'<a href="{maps_url}">Google Maps</a>' if maps_url else ""

    lines = [
        f"☕ <b>{cafe['name']}</b>",
        meta,
    ]
    if chips:
        lines.append(chips)
    if hours_line:
        lines.append(hours_line)
    if maps_line:
        lines.append(maps_line)

    return "\n".join(lines)


def _format_results(cafes: list[dict], query: str) -> str:
    if not cafes:
        return (
            "😕 No cafes found matching your search.\n\n"
            "Try removing a filter or broadening the area — "
            "I cover Westwood, Santa Monica, Venice, Culver City, Brentwood, Sawtelle, and more."
        )

    n = len(cafes)
    header = f"Here {'is' if n == 1 else 'are'} {n} cafe{'s' if n != 1 else ''} for you:\n"
    cards = "\n\n".join(_format_cafe(c) for c in cafes)
    return header + "\n" + cards


def send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> None:
    with httpx.Client() as client:
        client.post(
            f"{_TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
                  "disable_web_page_preview": True},
            timeout=10,
        )


def handle_update(update: dict) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id: int = message["chat"]["id"]
    text: str = (message.get("text") or "").strip()

    if not text:
        return

    if text.startswith("/start") or text.startswith("/help"):
        send_message(chat_id, _WELCOME)
        return

    # Strip any leading slash commands gracefully
    if text.startswith("/"):
        text = text.lstrip("/").strip()
        if not text:
            send_message(chat_id, _WELCOME)
            return

    # Parse + search
    filters = parse_query(text)
    search_mode = filters.pop("search_mode", "filter")
    limit = int(filters.get("limit", 6))

    if search_mode == "embedding":
        cafes = run_embedding_search(text, limit=limit)
        filters.pop("limit", None)
    elif search_mode == "hybrid":
        filter_results = run_search(dict(filters))
        if len(filter_results) >= limit:
            cafes = filter_results
        else:
            embed_results = run_embedding_search(text, limit=limit)
            seen = {r["place_id"] for r in filter_results}
            extras = [r for r in embed_results if r["place_id"] not in seen]
            cafes = (filter_results + extras)[:limit]
        filters.pop("limit", None)
    else:
        cafes = run_search(filters)

    reply = _format_results(cafes, text)
    send_message(chat_id, reply)
