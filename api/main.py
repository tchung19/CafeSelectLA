"""
CafeSelect API
==============
Run locally:
    uvicorn api.main:app --reload --port 8000

Docs at: http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.query_parser import parse_query
from api.search import run_search, run_embedding_search
from api.telegram_bot import handle_update

app = FastAPI(
    title="CafeSelect API",
    description="Intent-based cafe discovery for Los Angeles.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://cafe-select-la.vercel.app",
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str
    neighborhoods: list[str] = []


class SearchResponse(BaseModel):
    query: str
    filters: dict
    count: int
    results: list[dict]


@app.get("/health")
def health():
    return {"status": "poo"}


@app.get("/neighborhoods")
def neighborhoods():
    from api.search import _supabase
    rows = _supabase.table("cafes").select("neighborhood").execute().data or []
    counts: dict[str, int] = {}
    for r in rows:
        n = r.get("neighborhood")
        if n:
            counts[n] = counts.get(n, 0) + 1
    return {
        "neighborhoods": [
            {"name": n, "count": c}
            for n, c in sorted(counts.items(), key=lambda x: -x[1])
        ]
    }


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    filters = parse_query(req.query)
    search_mode = filters.pop("search_mode", "filter")
    limit = int(filters.get("limit", 6))

    if req.neighborhoods:
        filters.pop("neighborhood", None)
        filters["neighborhoods"] = req.neighborhoods

    if search_mode == "embedding":
        results = run_embedding_search(req.query, limit=limit)
        filters.pop("limit", None)
    elif search_mode == "hybrid":
        # Filters narrow candidates; embedding search fills gaps if needed
        filter_results = run_search(dict(filters))
        if len(filter_results) >= limit:
            results = filter_results
        else:
            embed_results = run_embedding_search(req.query, limit=limit)
            seen = {r["place_id"] for r in filter_results}
            extras = [r for r in embed_results if r["place_id"] not in seen]
            results = (filter_results + extras)[:limit]
        filters.pop("limit", None)
    else:
        results = run_search(filters)

    return SearchResponse(
        query=req.query,
        filters={"search_mode": search_mode, **filters},
        count=len(results),
        results=results,
    )


@app.post("/bot/telegram")
async def telegram_webhook(update: dict):
    handle_update(update)
    return {"ok": True}
