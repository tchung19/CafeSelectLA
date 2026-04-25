# CafeSelect

Yelp tells you a cafe's rating. It doesn't tell you if it has outlets, is quiet enough to take a call, or is still open in 2 hours when you need to finish your final.

CafeSelect does. Describe what you need: *"quiet spot in Westwood with outlets open till 9"* or *"aesthetic date cafe in Culver City"*, and get cafes that actually match.

**Status:** Data pipeline and search API complete, 53 cafes in Supabase. Telegram bot in progress.

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

api/
  main.py             FastAPI app — POST /search endpoint
  query_parser.py     Claude Haiku extracts structured filters from user query
  search.py           Supabase query builder with real-time hours filtering

bot/            Telegram bot (in progress)
web/            Web frontend (planned)

data/
  db_records/cafes.json   Merged records for all cafes
  cafes_review.csv        Review sheet
  search_log.json         Discovery run history
```

---

## Quickstart

**Requirements:** Python 3.11+, API keys for Google Places, Anthropic, and OpenAI.

```bash
git clone https://github.com/tchung19/CafeSelectLA
cd CafeSelectLA
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

## Search API

```bash
uvicorn api.main:app --reload --port 8000
```

`POST /search` — natural language query → structured Supabase filters → ranked cafe results.

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "quiet cafe in Westwood to work late"}'
```

Interactive docs at `http://localhost:8000/docs`.

The query parser uses Claude Haiku to extract filters (neighborhood, noise level, hours, etc.) from plain English. Hours filtering is computed dynamically against today's actual opening hours.

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
