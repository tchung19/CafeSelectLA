# CafeSelect

Intent-based cafe discovery for Los Angeles. Instead of star ratings and generic tags, CafeSelect answers questions like *"quiet spot to work near Westwood with outlets"* or *"aesthetic date cafe in Culver City"*.

**Status:** Data pipeline complete, 56 cafes in Supabase. Telegram bot in progress.

---

## How it works

```
Google Places API
  → Vision Pass A  (GPT-4o, per photo)
  → Vision Pass B  (Claude Sonnet, aggregates photos → cafe-level attributes)
  → LLM Extraction (Claude Haiku, extracts attributes from reviews + summaries)
  → DB Builder     (merges all sources into one structured record)
  → Supabase       (Postgres + pgvector for semantic search)
```

Each cafe ends up with ~100 structured attributes covering work-friendliness, vibe, food, seating, hours, and more — sourced from Google's structured data, AI review analysis, and direct photo analysis.

---

## Project structure

```
pipeline/
  discover.py           Find new cafe place_ids by neighborhood (text or grid mode)
  google_places.py      Google Places API client (search, details, photos)
  vision_pass_a.py      Per-photo GPT-4o analysis
  vision_pass_b.py      Claude Sonnet aggregator (photos → cafe-level JSON)
  llm_extractor.py      Claude Haiku attribute extraction from reviews
  run_llm_extractor.py  Batch runner for LLM extraction
  db_builder.py         Merge all sources into a single DB record
  pipeline.py           End-to-end orchestrator
  regions.py            Neighborhood → region mappings for West LA
  config.py             .env loading and key validation

api/            REST API (coming soon)
bot/            Telegram bot — MVP interface (coming soon)
web/            Web frontend (coming soon)

data/
  db_records/cafes.json   Merged records for all cafes
  cafes_review.csv        Review sheet
  search_log.json         Discovery run history
```

---

## Quickstart

**Requirements:** Python 3.11+, API keys for Google Places, Anthropic, and OpenAI.

```bash
git clone https://github.com/your-username/cafeselect
cd cafeselect
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
```

**Discover new cafes in a neighborhood:**
```bash
# Fast text search (~top 20 results)
python pipeline/discover.py --neighborhood westwood

# Grid search (~90% coverage)
python pipeline/discover.py --neighborhood westwood --mode grid --out new_ids.json

# All neighborhoods
python pipeline/discover.py --all --mode grid --out new_ids.json
```

**Run the full pipeline:**
```bash
python pipeline/pipeline.py \
  --ids-file new_ids.json \
  --data-dir data/cafes/ \
  --db-dir data/db_records/
```

**Run steps individually:**
```bash
# LLM extraction only (on already-fetched data)
python pipeline/run_llm_extractor.py --data-dir data/cafes/

# Build DB records only
python pipeline/db_builder.py --data-dir data/cafes/ --out-dir data/db_records/
```

---

## Attribute coverage

Each cafe record covers ~100 fields across 10 sections:

| Section | Source | Examples |
|---|---|---|
| Identity & Location | Google API | address, coordinates, neighborhood, region |
| Hours & Status | Google API | per-day hours, open after 5pm, open weekends |
| Ratings & Reviews | Google API | rating, review count, AI review summary |
| Google Structured | Google API | outdoor seating, dogs allowed, parking |
| Work & Study | LLM (reviews) | outlets score, wifi quality, study-friendly, noise level |
| Space & Physical | Vision (photos) | seating types, capacity, lighting, decor style |
| Vibe & Social | LLM + Vision | overall vibe tags, good for dates, instagrammable |
| Food & Drink | LLM + Vision | matcha, specialty drinks, signature items |
| Photos | Google API | photo URLs, hero photo |
| AI Content | (planned) | semantic summary, embedding for pgvector search |

---

## Cost per cafe

| Step | Model | Est. cost |
|---|---|---|
| Vision Pass A (10 photos) | GPT-4o | ~$0.20 |
| Vision Pass B | Claude Sonnet | ~$0.02 |
| LLM extraction | Claude Haiku (cached) | ~$0.01 |
| Google Places details | Places API | ~$0.017 |
| **Total** | | **~$0.25/cafe** |

---

## Coverage

Current focus: West LA — Westwood, Culver City, Brentwood, Santa Monica, Venice, Mar Vista, Sawtelle, and more. Expanding to Central LA and beyond.
