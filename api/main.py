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
from api.search import run_search

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
            {"name": n, "count": c} for n, c in sorted(counts.items())
        ]
    }


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    filters = parse_query(req.query)
    results = run_search(filters)

    return SearchResponse(
        query=req.query,
        filters=filters,
        count=len(results),
        results=results,
    )
