"""
CafeSelect — Vision Pass B: Claude Sonnet aggregator
=====================================================
Takes the per-photo JSON results from Pass A and synthesizes them into a
single cafe-level vision analysis JSON via Claude Sonnet 4.6.

Enforces null vs false semantics for has_outlets and seating capacity
zone-counting heuristics.

Callable as a module or standalone CLI.

Usage:
    python pipeline/vision_pass_b.py --per-photo-dir results/01_Upside_Down/per_photo --cafe-name "Upside Down" --out-dir results/01_Upside_Down
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY, require

require("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are CafeSelect's vision aggregator. You receive per-photo analysis JSON \
from multiple photos of a single cafe and synthesize them into a single \
cafe-level attribute JSON. You must cite which photo(s) support each attribute \
using evidence keys."""


def _build_user_prompt(cafe_name: str, per_photo: list[dict]) -> str:
    photos_text = "\n\n".join(
        f"=== Photo {i+1} ===\n{json.dumps(p, indent=2)}"
        for i, p in enumerate(per_photo)
    )
    return f"""\
Cafe name: "{cafe_name}"
Total photos analyzed: {len(per_photo)}

Per-photo analysis:
{photos_text}

Synthesize the above into a single cafe-level JSON. For each attribute, \
aggregate across all photos (e.g. outlets seen in ANY photo → has_outlets: true). \
Add an "_evidence" field citing which photo numbers support key attributes.

CRITICAL — null vs false:
- true  = confirmed present (seen in at least one photo)
- false = confirmed ABSENT (only if photos clearly prove it cannot exist)
- null  = not visible in photos, but cannot rule out — USE THIS as the default when nothing was detected
For has_outlets: if no outlets were seen in any photo, return null, not false. \
Outlets are rarely captured in cafe photos — not seeing them proves nothing.
If has_outlets is null, then outlet_confidence and outlet_count_estimate must also be null.

CRITICAL — seating_capacity:
Different photos show different parts of the same space — do NOT just take the max \
seats visible in any single frame. Use ALL of these signals together:
1. SUM seats across angles (photo 1 left side + photo 4 right side + photo 8 back area).
2. COUNT distinct seating zones — if 3+ different zones appear across photos (e.g. counter stools, sofa area, outdoor patio), the space is large (40+).
3. COUNT seating TYPE variety — if photos show 3+ different types (bean bags, sofas, stools, chairs, couches), it is a large multi-zone space.
4. TRUST adjectives in descriptions — if any photo description says "spacious", "large", "open", or "multi-zone", lean large.
5. DEFAULT bias: a full-size coffee shop with counter, multiple interior photos, and varied seating = medium (15-40) minimum. Tiny spaces are the exception, not the rule.

Return this schema:
{{
  "has_outlets": true/false/null,
  "outlet_confidence": "high|medium|low or null if has_outlets is null",
  "outlet_count_estimate": "none|few|many",
  "outlet_evidence": "e.g. photos 3 and 7 show wall outlets near seating",
  "has_wifi_signage": true/false/null,
  "seating_type": [],
  "seating_capacity": "small (<15)|medium (15-40)|large (40+)",
  "seating_density": "sparse|moderate|packed",
  "indoor_outdoor": "indoor|outdoor|both",
  "has_patio": true/false/null,
  "lighting": "bright_artificial|natural_light|dim_ambient|mixed",
  "decor_style": [],
  "noise_vibe": "quiet|moderate|lively|loud",
  "laptop_friendly": true/false/null,
  "laptop_users_visible": true/false,
  "laptop_evidence": "e.g. 2 laptop users in photo 4",
  "food_visible": [],
  "drink_types_visible": [],
  "has_display_case": true/false,
  "has_menu_board": true/false,
  "counter_service": true/false/null,
  "overall_vibe": ["exactly 3 distinctive tags based on what you see — free-form, lowercase, not generic"],
  "instagrammable": true/false,
  "instagram_confidence": "high|medium|low",
  "cleanliness": "clean|average|messy",
  "photo_types": [],
  "best_use_case": [],
  "photo_count_analyzed": {len(per_photo)},
  "notes": "any cross-photo observations not captured above"
}}

Return valid JSON only.
"""


def _parse_json(text: str) -> dict:
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:-1])
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"_parse_error": True, "_raw": text}


def run_pass_b(
    cafe_name: str,
    per_photo: list[dict],
    output_dir: Path,
) -> tuple[dict, dict]:
    """
    Aggregate per-photo Pass A results into a cafe-level vision JSON.
    Writes v2_aggregate.json to output_dir.
    Returns (analysis_dict, usage_dict).
    """
    prompt = _build_user_prompt(cafe_name, per_photo)

    response = _client.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    usage = {
        "input_tokens":  response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    result = _parse_json(response.content[0].text)

    # Enforce: if has_outlets is null, dependent fields must also be null
    if result.get("has_outlets") is None:
        result["outlet_confidence"]     = None
        result["outlet_count_estimate"] = None

    out = {
        "cafe_name":          cafe_name,
        "model":              MODEL,
        "photos_aggregated":  len(per_photo),
        "timestamp":          datetime.now().isoformat(),
        "usage":              usage,
        "analysis":           result,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "v2_aggregate.json", "w") as f:
        json.dump(out, f, indent=2)

    return result, usage


def load_per_photo_dir(per_photo_dir: Path) -> list[dict]:
    """Load all photo_N.json files from a per_photo directory."""
    files = sorted(per_photo_dir.glob("photo_*.json"))
    results = []
    for fp in files:
        with open(fp) as f:
            data = json.load(f)
        # Each file has {"photo": ..., "analysis": {...}, "usage": {...}}
        results.append(data.get("analysis", data))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Vision Pass B (Claude Sonnet aggregator) on per-photo Pass A results."
    )
    parser.add_argument("--per-photo-dir", required=True, metavar="DIR",
                        help="Directory containing photo_N.json files from Pass A")
    parser.add_argument("--cafe-name", required=True, metavar="NAME",
                        help="Display name of the cafe")
    parser.add_argument("--out-dir", required=True, metavar="DIR",
                        help="Output directory for v2_aggregate.json")
    args = parser.parse_args()

    per_photo_dir = Path(args.per_photo_dir)
    out_dir       = Path(args.out_dir)

    per_photo = load_per_photo_dir(per_photo_dir)
    if not per_photo:
        print(f"❌ No photo_N.json files found in {per_photo_dir}")
        return

    print(f"\n{'='*55}")
    print(f"  Vision Pass B — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Cafe: {args.cafe_name}  |  Photos: {len(per_photo)}")
    print(f"{'='*55}\n")

    result, usage = run_pass_b(args.cafe_name, per_photo, out_dir)
    cost = (usage["input_tokens"] * 3.00 + usage["output_tokens"] * 15.00) / 1_000_000
    print(f"  Tokens: input={usage['input_tokens']}  output={usage['output_tokens']}")
    print(f"  Est cost: ${cost:.4f}")
    print(f"\n✅ Aggregate → {out_dir / 'v2_aggregate.json'}\n")


if __name__ == "__main__":
    main()
