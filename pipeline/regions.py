"""
CafeSelect — Region & Neighborhood Mappings
=============================================
Single source of truth for:
  - Neighborhood → region bucketing
  - ZIP code → neighborhood fallback lookup
  - Neighborhood extraction from Google Place details
"""

import re

# ── Region sets ───────────────────────────────────────────────────────────────

WEST_LA = {
    "Westwood", "Brentwood", "Santa Monica", "Venice", "Culver City",
    "Mar Vista", "West Los Angeles", "Sawtelle", "Palms", "Pacific Palisades",
    "Century City", "Bel-Air", "Cheviot Hills", "Marina del Rey",
    "Playa Vista", "Playa del Rey",
}
CENTRAL_LA = {
    "Silver Lake", "Echo Park", "Downtown", "Downtown Los Angeles",
    "Los Feliz", "Hollywood", "East Hollywood", "Koreatown",
    "West Adams", "Mid-City", "Pico-Robertson", "Fairfax", "Mid-Wilshire",
    "Larchmont", "Hancock Park",
}
SOUTH_LA = {
    "South Los Angeles", "Watts", "Inglewood", "Leimert Park", "Hyde Park",
    "Crenshaw", "Baldwin Hills",
}
VALLEY = {
    "Sherman Oaks", "Studio City", "North Hollywood", "Burbank", "Glendale",
    "Encino", "Tarzana", "Woodland Hills", "Van Nuys", "Reseda",
}

# ── ZIP → neighborhood ────────────────────────────────────────────────────────

ZIP_TO_NEIGHBORHOOD: dict[str, str] = {
    # Westwood / UCLA
    "90024": "Westwood",
    # Brentwood
    "90049": "Brentwood",
    # Sawtelle / West LA
    "90025": "Sawtelle",
    "90064": "Rancho Park",
    # Palms
    "90034": "Palms",
    # Mar Vista / Del Rey
    "90066": "Mar Vista",
    # Venice
    "90291": "Venice",
    # Marina del Rey
    "90292": "Marina del Rey",
    # Playa del Rey
    "90293": "Playa del Rey",
    # Playa Vista
    "90094": "Playa Vista",
    # Culver City
    "90230": "Culver City",
    "90232": "Culver City",
    # Century City
    "90067": "Century City",
    # Pacific Palisades
    "90272": "Pacific Palisades",
    # Santa Monica
    "90401": "Santa Monica",
    "90402": "Santa Monica",
    "90403": "Santa Monica",
    "90404": "Santa Monica",
    "90405": "Santa Monica",
    # West Adams / Mid-City
    "90016": "West Adams",
    "90018": "West Adams",
    "90019": "Mid-City",
    "90035": "Pico-Robertson",
    # Koreatown
    "90005": "Koreatown",
    "90006": "Koreatown",
    "90010": "Koreatown",
}

# ── Functions ─────────────────────────────────────────────────────────────────

def region_from_neighborhood(neighborhood: str | None) -> str | None:
    if not neighborhood:
        return None
    if neighborhood in WEST_LA:
        return "West LA"
    if neighborhood in CENTRAL_LA:
        return "Central LA"
    if neighborhood in SOUTH_LA:
        return "South LA"
    if neighborhood in VALLEY:
        return "San Fernando Valley"
    return None


# Cities that ARE the neighborhood (independent cities, not LA sub-areas)
_CITY_AS_NEIGHBORHOOD = {"Culver City", "Santa Monica", "Burbank", "Glendale", "Inglewood"}


def extract_neighborhood(details: dict) -> str | None:
    """
    Pull neighborhood from a Google Place details dict.
    Four-stage fallback:
      1. addressComponents neighborhood/sublocality — but skip if unknown micro-neighborhood
      2. addressComponents locality — catches independent cities (Culver City, Santa Monica)
      3. formattedAddress parse (works when neighborhood is explicit in the string)
      4. ZIP code lookup (covers plain 'City, CA ZIP' addresses)
    """
    components = details.get("addressComponents", []) or []
    locality = None
    sub_neighborhood = None

    for comp in components:
        types = comp.get("types", [])
        if "locality" in types:
            locality = comp.get("longText") or comp.get("shortText")
        if "neighborhood" in types or "sublocality" in types or "sublocality_level_1" in types:
            sub_neighborhood = comp.get("longText") or comp.get("shortText")

    # 1. If locality is a city we treat as a neighborhood, prefer it — avoids
    #    "Downtown Culver City" matching the LA Downtown set
    if locality in _CITY_AS_NEIGHBORHOOD:
        return locality

    # 2. Sub-neighborhood — only use if it's in our known region set
    if sub_neighborhood and region_from_neighborhood(sub_neighborhood):
        return sub_neighborhood

    addr = details.get("formattedAddress", "")

    # 3. Explicit neighborhood token in formatted address
    parts = [p.strip() for p in addr.split(",")]
    for i, part in enumerate(parts):
        if "Los Angeles" in part and i > 0:
            candidate = parts[i - 1]
            if not re.match(r"^\d", candidate):
                return candidate

    # 4. ZIP code lookup — anchored to "CA " to avoid matching street numbers
    zip_match = re.search(r"\bCA\s+(\d{5})\b", addr)
    if zip_match:
        return ZIP_TO_NEIGHBORHOOD.get(zip_match.group(1))

    return locality  # last resort: return whatever locality we found
