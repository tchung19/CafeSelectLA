"""
CafeSelect API
==============
Run locally:
    uvicorn api.main:app --reload --port 8000

Docs at: http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from api.query_parser import parse_query
from api.search import run_search

app = FastAPI(
    title="CafeSelect API",
    description="Intent-based cafe discovery for Los Angeles.",
    version="0.1.0",
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
    return {"status": "ok"}


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
