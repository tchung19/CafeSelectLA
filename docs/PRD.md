# CafeSelect — Product Requirements Document

**Author:** TC
**Last updated:** April 20, 2026
**Status:** Draft v2

---

## 1. Overview

CafeSelect is an intent-based cafe discovery tool for Los Angeles. Instead of starting from a map or a name, users describe *what they want to do* — "study", "date night", "grab matcha", "work with laptop open till 9PM" — and get a curated list of cafes that match.

The underlying product is a **structured, LLM-enriched database** of LA cafes, with attributes extracted from Google Maps data (reviews, photos, hours). This database is exposed through a **REST API**, which any surface — a bot, a website, a mobile app — can call.

**CafeSelect is built API-first.** The database and API are the product. The surfaces are interchangeable.

**MVP is a Telegram bot.** A user sends a message like "quiet cafe with outlets in Westwood open till 9" and gets back a ranked list of matching cafes with key attributes. The web frontend comes after the bot is live and validated.

**MVP scope is West LA only** (Culver City, Santa Monica, Westwood, Venice, Mar Vista, Palms, Century City, Brentwood). The architecture, schema, and API are designed so additional regions — and eventually other cities — are added by re-running the data pipeline, with zero changes to the bot or frontend.

---

## 2. Problem Statement

Existing tools fail at intent-based cafe discovery:

- **Google Maps** filters by hours and a handful of attributes (wifi, dine-in) but cannot answer "has outlets", "good for studying", or "serves great avocado toast".
- **Yelp** surfaces review-text matches but has no structured, filterable attribute layer. It is fundamentally a review platform, not a discovery tool.
- **Workfrom.co** validated the "laptop-friendly cafe database" market pre-COVID with 100K+ users, but pivoted to virtual coworking and stalled.
- **LaptopFriendlyCafe.com** exists for LA but is a static curated list with no search or filtering.

Specific pain points from real LA residents:

- "I need a cafe open past 8PM with outlets" — not filterable anywhere.
- "I want a quiet place to study in Koreatown" — requires reading 20+ reviews per cafe.
- "I want a cafe with great avocado toast" — requires trawling review text or photos manually.
- "I want a date-night cafe with good atmosphere" — entirely invisible to keyword search.

All of this information exists inside Google reviews and photos today. None of it has been extracted into a queryable, structured form.

---

## 3. Goals & Non-Goals

### Goals

- Let users find a matching cafe in under 30 seconds via a Telegram or WhatsApp bot.
- Build a defensible, structured attribute database that competitors cannot replicate without running a similar LLM pipeline.
- Expose all data through a clean REST API so any future surface (web, mobile, other bots) can plug in without touching the database layer.
- Demonstrate end-to-end product thinking: problem → data architecture → API design → shipped product. This is a portfolio artifact for tech PM recruiting.

### Non-Goals (MVP)

- Web frontend. The website is Phase 4, not MVP.
- Reviews, user accounts, or social features.
- Reservations, ordering, or transactions.
- Mobile app.
- LA regions outside **West LA**.
- Cities outside Los Angeles.
- Real-time data (hours are derived from stored data, not live-polled).

---

## 4. Target User

**Primary:** LA residents ages 20–40 who work remotely, study, or socialize in cafes. They have a specific use case ("I need two hours of focused work") and want a curated answer fast — not 50 Yelp results to sift through.

**Secondary (portfolio):** Tech PM recruiters evaluating the builder's ability to ship a real, working product with clear architectural thinking.

---

## 5. Competitive Landscape

| Product | Strength | Why it doesn't solve this |
|---|---|---|
| Google Maps | Comprehensive cafe list, hours, ratings | No intent-based attributes (study, outlets, vibe) |
| Yelp | Reviews, photos, text search | No structured filterable attributes |
| Workfrom.co | Validated demand pre-COVID | Stalled; pivoted away from cafe database |
| LaptopFriendlyCafe.com | LA-specific curated list | Static; no search or filter engine |
| Lemon8 | UGC cafe content | Social feed; not queryable or structured |

**Differentiation:** CafeSelect is the only product organizing cafes around **structured, AI-extracted intent attributes** rather than around reviews or location.

---

## 6. Product Scope

### 6.1 Architecture Principle: API-First

Every feature is built as an API endpoint first. The bot consumes the API. The future website consumes the same API. No surface has direct database access — everything goes through the API layer.

```
User (Telegram / WhatsApp / Web)
        ↓
    Surface Layer  (bot handler / Next.js frontend)
        ↓
    NLP Layer  (LLM parses natural language → structured query params)
        ↓
    CafeSelect REST API  (/api/cafes, /api/search)
        ↓
    Supabase  (Postgres + pgvector)
```

This means the website in Phase 4 requires zero new backend work — it just calls the same API the bot already uses.

### 6.2 API Endpoints (MVP)

These three endpoints power everything — the bot, and later the web frontend.

**`GET /api/cafes`** — filtered list query

```
Query params:
  neighborhood      string        e.g. "westwood", "santa-monica"
  region            string        e.g. "west-la"
  study_friendly    boolean
  has_outlets       boolean
  noise_level       quiet | moderate | loud
  open_after        string        e.g. "21:00"
  open_now          boolean
  has_matcha        boolean
  has_avocado_toast boolean
  good_for_dates    boolean
  outdoor_seating   boolean
  dog_friendly      boolean
  limit             int           default 5, max 20
  offset            int           for pagination

Response: array of cafe objects with name, neighborhood, matched attributes,
          rating, hours_today, hero_photo_url
```

**`GET /api/cafes/:id`** — single cafe detail

```
Response: full cafe object — all attributes, confidence scores,
          full photo array, hours (all days), AI summary, google_place_id
```

**`POST /api/search`** — semantic / natural language search

```
Body: { "query": "cozy place to read with good matcha", "neighborhood": "westwood" }

Response: same shape as GET /api/cafes, ranked by vector similarity score
```

### 6.3 MVP Surface: Telegram Bot

The bot is the first user-facing product. A user messages the bot in natural language. The bot:

1. Receives the message via Telegram webhook
2. Passes it to the **NLP parsing layer** (GPT-4o mini) which converts it to structured query params
3. Calls `GET /api/cafes` or `POST /api/search` with those params
4. Formats the response and replies

**Example conversation:**

```
User:   quiet study cafe in westwood with outlets, open till 9

Bot:    Here are 3 cafes matching your search in Westwood:

        ☕ Stella Coffee Westwood
        📍 Westwood · ⭐ 4.9
        🔌 Has outlets · 🤫 Quiet · 🕘 Open until 10PM
        📚 Study-friendly · ☕ Specialty coffee

        ☕ Boondocks Coffee Roasters
        📍 Westwood · ⭐ 4.7
        🤫 Quiet · 📚 Study-friendly · 🍵 Great matcha
        🕘 Open until 9PM

        ☕ Driply Coffee Space
        📍 Westwood · ⭐ 5.0
        📚 Study-friendly · ☕ Specialty coffee
        🕘 Open until 8PM

        Reply with a cafe name for full details, or
        try: "show me ones with outdoor seating"
```

**Follow-up commands the bot handles:**

- `"more"` → next page of results
- `"[cafe name]"` → call `GET /api/cafes/:id`, return full details
- `"show me ones with outdoor seating"` → re-run query with added filter
- `"matcha cafes near UCLA"` → new search, same NLP flow

**Platform choice:** Telegram for MVP (no approval process, free, simple webhook API). WhatsApp (via Twilio) is Phase 3B — same bot logic, different platform adapter.

### 6.4 NLP Parsing Layer

Between the bot and the API sits a lightweight LLM call that converts natural language into structured query params.

```python
# Input: user's raw message
# Output: structured JSON matching GET /api/cafes query params

prompt = """
Convert this cafe search request into a JSON query object.

Available filters:
{
  "neighborhood": string,         // e.g. "westwood", "santa-monica", "culver-city"
  "region": string,               // e.g. "west-la" (use if no specific neighborhood)
  "study_friendly": boolean,
  "has_outlets": boolean,
  "noise_level": "quiet" | "moderate" | "loud",
  "open_after": "HH:MM",         // 24h format, e.g. "21:00" for "open till 9"
  "open_now": boolean,
  "has_matcha": boolean,
  "has_avocado_toast": boolean,
  "good_for_dates": boolean,
  "outdoor_seating": boolean,
  "dog_friendly": boolean
}

User message: "{user_message}"

Return only the JSON fields that are clearly implied. Return valid JSON only.
"""
```

**Model:** GPT-4o mini (cheap, fast — this runs on every user message).

**Cost per query:** ~500 tokens × $0.00015/1K tokens ≈ $0.00008. Negligible.

### 6.5 Phase 4 Surface: Web Frontend

The web frontend is a search-first discovery interface built on Next.js, deployed on Vercel. It calls the same API endpoints the bot uses — no new backend work.

Homepage: search bar + intent tag row (Studying, Matcha, Date Night, Outdoor, Open Late, Great Food, Aesthetic) + nested location picker (Region → Neighborhood).

Results page: cafe cards with hero photo, matched attribute chips, rating, hours status.

Cafe detail page: full attributes with confidence scores, photo gallery, AI summary, embedded map, link out to Google Maps.

### 6.6 Location Model

| Region | Neighborhoods (MVP in **bold**) |
|---|---|
| **West LA** | **Culver City, Santa Monica, Westwood, Venice, Mar Vista, Palms, Century City, Brentwood** |
| Central LA | Koreatown, Silver Lake, Echo Park, Los Feliz, Hollywood, Mid-Wilshire |
| DTLA | Downtown, Arts District, Little Tokyo, Chinatown |
| Eastside | Highland Park, Eagle Rock, Atwater Village |
| South Bay | Manhattan Beach, Hermosa Beach, Redondo Beach, El Segundo |
| San Fernando Valley | Studio City, Sherman Oaks, Burbank, North Hollywood |

Only West LA is populated at MVP. The bot gracefully handles out-of-scope requests: `"I only cover West LA neighborhoods right now. Try Westwood, Santa Monica, Culver City, Venice, or Brentwood."

### 6.7 Core Filterable Attributes

| Category | Attribute |
|---|---|
| Hours | Open now, Open after 8PM, Open weekends |
| Work-friendly | Has outlets (0–5 score), Wifi quality (0–5), Noise level (quiet/moderate/loud), Study-friendly (boolean) |
| Space | Outdoor seating, Seating capacity (small/medium/large), Dog-friendly |
| Food/Drink | Has matcha, Has avocado toast, Has specialty coffee, Has food |
| Vibe | Good for dates, Instagrammable, Parking nearby |
| Location | Region, Neighborhood |

Every LLM-derived attribute carries a **confidence score** and **mention count**. The API only returns attributes above a confidence threshold; the bot only surfaces the top 3–4 matched attributes per cafe.

---

## 7. Technical Architecture

### 7.1 Full Stack

| Layer | Tool | Rationale |
|---|---|---|
| Data source | Google Places API + Photos API | Authoritative, ToS-compliant, free within monthly credit |
| LLM enrichment (text) | GPT-4o mini | Cheap, fast, accurate for structured JSON extraction from reviews |
| LLM enrichment (vision) | GPT-4o | Best-in-class vision for outlet/seating/food detection from photos |
| NLP query parsing | GPT-4o mini | Converts user messages → structured API params; runs on every query |
| Database | Supabase (Postgres + pgvector) | Managed, free tier, native vector search |
| API | Next.js API Routes | Serverless, colocated with future frontend, no separate backend |
| Bot platform (MVP) | Telegram Bot API | Free, no approval process, simple webhook setup |
| Bot platform (Phase 3B) | Twilio WhatsApp API | Same bot logic, different adapter |
| Frontend (Phase 4) | Next.js on Vercel | Same repo as API; auto-deploys from GitHub |
| Version control | GitHub | Code + schema + pipeline + portfolio showcase |

No Algolia, no Docker, no separate backend, no custom domain for MVP.

### 7.2 Data Pipeline

```
Google Places API  →  Raw cafe data (name, address, hours, rating, attributes)
        ↓
Google Reviews/Photos API  →  Review text (5/cafe) + hero photos (3/cafe)
        ↓
Google AI Summaries  →  Pre-condensed review synthesis (where available)
        ↓
GPT-4o mini (text)  →  Structured attributes + confidence scores from reviews + summaries
        ↓
GPT-4o Vision  →  Seating type, vibe, food items, outlet detection from photos
        ↓
Embedding model  →  pgvector embeddings per cafe (for semantic search)
        ↓
Supabase (Postgres)  →  Queryable product database
        ↓
REST API  →  Consumed by bot and (later) web frontend
```

The pipeline runs as a local Python script for MVP. It can be moved to a GitHub Actions scheduled job post-launch without architectural change.

**Key finding from API test (April 20, 2026):** Google's 5 reviews per cafe and Google AI summaries are complementary — raw reviews catch outlets/wifi/noise (which summaries miss), while summaries synthesize vibe/food from the full review corpus. Both sources should feed the LLM enrichment step. SSL stability requires Python 3.11+.

### 7.3 Data Model

**`cafes` table** — one row per cafe

Core fields: `id`, `name`, `address`, `region`, `neighborhood`, `lat`, `lng`, `google_place_id`, `google_rating`, `review_count`, `price_level`, `website`, `phone`, `hours` (JSON by day), `ai_summary`, `updated_at`

Derived hour booleans: `open_after_8pm`, `open_weekends`

LLM-enriched attributes (each with `_confidence` float and `_mentions` int): `has_outlets`, `outlet_score`, `wifi_quality`, `noise_level`, `study_friendly`, `outdoor_seating`, `seating_capacity`, `dog_friendly`, `good_for_dates`, `instagrammable`, `parking_nearby`, `has_matcha`, `has_avocado_toast`, `has_specialty_coffee`, `has_food`

Vector field: `embedding` (pgvector, for semantic search)

**`photos` table** — many per cafe

Fields: `cafe_id`, `url`, `type` (interior/food/drinks/exterior), `ai_labels` (JSON array), `is_hero`

**`regions` / `neighborhoods` tables** — reference data for the location hierarchy. Neighborhoods are assigned to each cafe during enrichment via lat/lng + LA Times Mapping LA boundary polygons.

**Deliberate exclusions:** raw review text is not stored verbatim. We store the AI-generated summary and extracted attributes. `google_place_id` is kept so source data can always be re-fetched.

---

## 8. Success Metrics

### Bot metrics

- Messages per active user
- Query-to-result success rate (did the NLP parse produce valid API results)
- Follow-up rate (did user engage after first result)
- Top intents by frequency (which tags/attributes are queried most)

### Portfolio metrics (the real measure for MVP)

- Bot is live, shareable, and works end-to-end for a recruiter who messages it
- Public GitHub repo with documented pipeline, schema, API spec, and architecture decisions
- At least 200 West LA cafes in the database with enriched attributes
- Clear write-up of PM decisions (why bot-first, why API-first, why pgvector, cost tradeoffs)

---

## 9. Roadmap

### Phase 0 — Foundation (Week 1)
- Set up Supabase project, define schema, commit `schema.sql` to GitHub
- Set up Next.js project on Vercel (placeholder only — API routes scaffolded)
- Obtain Google Places API key; verify per-SKU free-tier quota limits (updated March 2025)
- Fix Python SSL issue (upgrade to Python 3.11+ or add retry wrapper)

### Phase 1 — Data Pipeline, West LA (Weeks 2–3)
- Build Python scraper: Google Places text search scoped to West LA neighborhoods
- Pull Place Details (reviews, hours, photos, structured attributes, AI summaries)
- Assign each cafe to region + neighborhood via lat/lng + polygon match
- Run GPT-4o mini text enrichment: reviews + AI summaries → structured attributes + confidence scores
- Run GPT-4o vision enrichment: 2–3 photos/cafe → seating/vibe/food/outlet detection
- Generate embeddings per cafe; store in pgvector
- **Target: 200–300 West LA cafes enriched by end of phase**

### Phase 2 — API Layer (Week 4)
- Build and deploy three API endpoints in Next.js:
  - `GET /api/cafes` (filtered list)
  - `GET /api/cafes/:id` (cafe detail)
  - `POST /api/search` (semantic / vector search)
- Write API spec in `README.md`
- Test all endpoints manually against the West LA dataset

### Phase 3A — Telegram Bot MVP (Week 5)
- Set up Telegram Bot via BotFather; configure webhook to `/api/bot/telegram`
- Build NLP parsing layer: GPT-4o mini converts user message → structured query params
- Wire parsed params to `GET /api/cafes` or `POST /api/search`
- Format and return top 5 results with attribute chips
- Handle follow-up commands: detail request, pagination, filter refinement
- **Bot is live and shareable. This is the MVP.**

### Phase 3B — WhatsApp Bot (Week 6)
- Set up Twilio WhatsApp sandbox
- Build WhatsApp adapter (same bot logic as Telegram, different message format)
- Wire to same API endpoints
- Deploy webhook to `/api/bot/whatsapp`

### Phase 4 — Web Frontend (Weeks 7–8)
- Homepage: search bar + intent tag row + nested location picker
- Results page: cafe cards with hero photo, matched attribute chips, rating, hours
- Cafe detail page: full attributes, photo gallery, AI summary, embedded map
- Mobile responsive pass
- **Same API the bot uses — zero new backend work**

### Phase 5 — Expand LA Coverage (post-launch, by region)
- Central LA next (Koreatown, Silver Lake, Echo Park, Hollywood) — highest expected demand
- Then DTLA, Eastside, South Bay, Valley in order of cafe density
- **Each region = pipeline re-run only. No changes to API, bot, or frontend.**

### Post-MVP ideas (not committed)
- Expand to NYC, SF
- User-submitted attribute corrections
- "Surprise me" mode via embeddings
- Weekly newsletter of featured cafes by neighborhood

---

## 10. Risks & Open Questions

| Risk | Mitigation |
|---|---|
| Google Places per-SKU pricing surprise | Verify exact free-tier limits before Phase 1 batch run; cap to 300 cafes initially |
| LLM enrichment quality inconsistent | Store confidence + mention count; only surface high-confidence attrs in API response |
| Vision adds cost without enough signal | Outlets are hard to detect visually; rely on review text as primary source, vision as supplement |
| NLP parsing misinterprets user intent | Log all parsed queries; tune prompt based on failure patterns |
| Google Photos URLs expire | Download photos locally during pipeline; store to Supabase storage |
| Data goes stale | Store `updated_at`; plan monthly refresh cron post-MVP |
| Telegram bot goes down | Vercel serverless is stateless — bot handler is just an API route, restarts automatically |

**Open questions to resolve before Phase 1:**

- Exact confidence threshold for surfacing an attribute in API responses
- Whether to run vision enrichment on all 200 cafes upfront or only on cafes with low text-enrichment confidence
- Google Places per-SKU free tier limits (changed March 2025 — needs verification)

---

## 11. Appendix — Key Product Decisions

**Bot-first, not web-first.** A bot is faster to ship, easier to share with recruiters (one link, one message), and tests the core data layer without building a full UI. The web frontend comes after the data and API are validated.

**API-first architecture.** The database and API are the product. The bot and website are surfaces. This means Phase 4 (web) requires zero new backend work — the same three API endpoints the bot calls power the entire site. It also means future surfaces (mobile app, Slack bot, LINE) are just new adapters.

**Search-first UI over map-first UI.** Pain points are intent-based ("I need to study"), not location-based ("what's near me"). A map is the wrong mental model for this problem.

**Supabase + pgvector over Algolia.** Semantic "vibe search" is a differentiating feature directly enabled by the enrichment pipeline. Algolia adds sync complexity and no product differentiation.

**GPT-4o mini for text enrichment and NLP parsing; GPT-4o for vision.** Text extraction is a straightforward task — cheap models handle it well (< $2 for the full LA dataset). Vision requires a stronger model for reliable spatial/object detection.

**Telegram before WhatsApp.** Telegram has no approval process, free tier, and a simpler webhook API. WhatsApp via Twilio adds credential and cost overhead. Same bot logic, different adapter — the switch is a one-week add-on after the core is proven.

**West LA first, not all of LA.** Quality over breadth: 250 deeply-enriched West LA cafes outperforms 2,000 shallow ones city-wide. The "coming soon" treatment for other regions telegraphs the expansion roadmap without committing to it.

**Free-tier everything.** Keeps cost near $0/month and demonstrates cost-conscious architecture thinking — a PM skill, not just a dev skill.

**The database is the product.** The pipeline is the moat. Anyone can build a Next.js frontend or a Telegram bot in a weekend. The structured, LLM-enriched, confidence-scored attribute database is what takes time and thinking to build — and what competitors cannot quickly replicate.
