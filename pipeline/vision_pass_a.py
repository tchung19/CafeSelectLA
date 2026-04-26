"""
CafeSelect — Vision Pass A: per-photo GPT-4o analysis
=======================================================
One GPT-4o call per photo. Returns factual-only structured JSON
describing only what is directly visible in that photo.

Callable as a module or standalone CLI.

Usage:
    python pipeline/vision_pass_a.py --cafe-dir data/cafes/01_Upside_Down --out-dir results/01_Upside_Down
"""

from __future__ import annotations

import argparse
import base64
import json
import time
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from config import settings, require

require("OPENAI_API_KEY", settings.openai_api_key)

_client = OpenAI(api_key=settings.openai_api_key)

MODEL = "gpt-4o"

PROMPT = """\
Analyze this single cafe photo and return a JSON object with only what you can \
directly observe in THIS photo. Do not infer or speculate.

Return this exact schema (use null for anything not visible):
{
  "photo_type": "interior|exterior|food|drinks|menu|staff|other",
  "outlets_visible": {
    "count": 0,
    "locations": [],
    "confidence": "none|low|medium|high"
  },
  "seating": {
    "types": [],
    "count_estimate": null
  },
  "laptops_visible": 0,
  "people_count_approx": 0,
  "food_items": [],
  "drinks": [],
  "wifi_signage": false,
  "description": "1-2 sentence factual description of exactly what is in this photo"
}

For outlets_visible.locations, use short labels like "wall behind counter", \
"floor near seating area", "under window ledge".
Return valid JSON only. No explanation.
"""


def _encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _parse_json(text: str) -> dict:
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:-1])
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"_parse_error": True, "_raw": text}


def analyze_photo(photo_path: Path) -> tuple[dict, dict]:
    """
    Analyze a single photo with GPT-4o.
    Returns (analysis_dict, usage_dict).
    """
    b64 = _encode_image(photo_path)
    response = _client.chat.completions.create(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                {"type": "text", "text": PROMPT},
            ],
        }],
        max_tokens=400,
        temperature=0.1,
    )
    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    }
    return _parse_json(response.choices[0].message.content), usage


def run_pass_a(
    cafe_dir: Path,
    output_dir: Path,
    sleep_between: float = 0.3,
) -> tuple[list[dict], dict]:
    """
    Run Pass A on all photos in cafe_dir/photos/.
    Writes per_photo/photo_N.json to output_dir.
    Returns (list_of_analysis_dicts, total_usage).
    """
    photos_dir = cafe_dir / "photos"
    photos = sorted(photos_dir.glob("photo_*.jpg"))
    per_photo_dir = output_dir / "per_photo"
    per_photo_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    for i, photo_path in enumerate(photos, 1):
        print(f"    Pass A — photo {i}/{len(photos)}: {photo_path.name}")
        result, usage = analyze_photo(photo_path)

        out = {"photo": photo_path.name, "analysis": result, "usage": usage}
        with open(per_photo_dir / f"photo_{i}.json", "w") as f:
            json.dump(out, f, indent=2)

        results.append(result)
        total_usage["prompt_tokens"]     += usage["prompt_tokens"]
        total_usage["completion_tokens"] += usage["completion_tokens"]
        time.sleep(sleep_between)

    return results, total_usage


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Vision Pass A (per-photo GPT-4o) on a cafe's photos."
    )
    parser.add_argument("--cafe-dir", required=True, metavar="DIR",
                        help="Cafe directory containing photos/")
    parser.add_argument("--out-dir", required=True, metavar="DIR",
                        help="Output directory for per_photo/ JSONs")
    args = parser.parse_args()

    cafe_dir = Path(args.cafe_dir)
    out_dir  = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*55}")
    print(f"  Vision Pass A — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Cafe: {cafe_dir.name}")
    print(f"{'='*55}\n")

    results, usage = run_pass_a(cafe_dir, out_dir)
    cost = (usage["prompt_tokens"] * 2.50 + usage["completion_tokens"] * 10.00) / 1_000_000
    print(f"\n  Photos: {len(results)}")
    print(f"  Tokens: prompt={usage['prompt_tokens']}  completion={usage['completion_tokens']}")
    print(f"  Est cost: ${cost:.4f}")
    print(f"\n✅ Results → {out_dir / 'per_photo'}\n")


if __name__ == "__main__":
    main()
