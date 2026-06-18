"""
Cikk lekérdezések.

GET /api/v1/articles              – szűrt + paginált cikk lista (FTS5 keresés)
GET /api/v1/articles/{article_id} – egyetlen cikk részletei
GET /api/v1/articles/{article_id}/trend – kulcsszó trend (utolsó N futás)
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ikon.api.dependencies import get_db
from ikon.api.schemas import ArticleOut, PaginatedResponse
from ikon.repository import ArticleFilter, ArticleRepository

router = APIRouter(tags=["articles"])


def _to_article_out(d: dict) -> ArticleOut:
    kws = d.get("matched_keywords", [])
    if isinstance(kws, str):
        import json
        try:
            kws = json.loads(kws)
        except Exception:
            kws = []
    return ArticleOut(
        article_id=d.get("article_id", ""),
        run_id=d.get("run_id", ""),
        url=d.get("url", ""),
        title=d.get("title") or "",
        source=d.get("source") or "",
        source_type=d.get("source_type") or "egyéb",
        published_date=d.get("published_date") or "",
        published_date_iso=d.get("published_date_iso"),
        published_time=d.get("published_time") or "",
        excerpt=d.get("excerpt") or "",
        matched_keywords=kws,
        best_tier=d.get("best_tier") or "",
        score=d.get("score") or 0,
        score_reason=d.get("score_reason") or "",
        category=d.get("category") or "",
        feedback_decision=d.get("feedback_decision"),
        reviewer_id=d.get("reviewer_id"),
        reviewer_note=d.get("reviewer_note"),
        scored_at=d.get("scored_at") or "",
    )


@router.get("/articles", response_model=PaginatedResponse[ArticleOut])
def list_articles(
    run_id: Optional[str] = Query(default=None, description="Pipeline futás ID"),
    category: Optional[str] = Query(default=None, description="releváns | felülvizsgálandó | zaj"),
    source_type: Optional[str] = Query(default=None, description="médiaipari | bulvár | egyéb"),
    best_tier: Optional[str] = Query(default=None),
    score_min: Optional[int] = Query(default=None, ge=0, le=100),
    score_max: Optional[int] = Query(default=None, ge=0, le=100),
    date_from: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    search: Optional[str] = Query(default=None, description="FTS5 keresési lekérdezés (title + excerpt)"),
    has_feedback: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> PaginatedResponse[ArticleOut]:
    """Cikkek szűrt + paginált listája.

    A `search` paraméter SQLite FTS5 szintaxist támogat:
    - `TV2 nézettség` – mindkét szó jelenléte
    - `"IKO Műsorgyártó"` – pontos kifejezés
    - `médiapiac OR hirdetés` – OR keresés
    """
    f = ArticleFilter(
        run_id=run_id,
        category=category,
        source_type=source_type,
        best_tier=best_tier,
        score_min=score_min,
        score_max=score_max,
        date_from=date_from,
        date_to=date_to,
        search=search,
        has_feedback=has_feedback,
        limit=limit,
        offset=offset,
    )
    page = ArticleRepository(conn).list(f)
    return PaginatedResponse(
        items=[_to_article_out(d) for d in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        has_more=page.has_more,
    )


@router.get("/articles/{article_id}", response_model=ArticleOut)
def get_article(
    article_id: str,
    run_id: Optional[str] = Query(default=None, description="Ha megadott, adott futás verzióját adja"),
    conn: sqlite3.Connection = Depends(get_db),
) -> ArticleOut:
    """Egyetlen cikk teljes adatai. Alapértelmezés: legutóbbi futás verziója."""
    d = ArticleRepository(conn).get(article_id, run_id=run_id)
    if not d:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Cikk nem található: {article_id}", "code": "NOT_FOUND"},
        )
    return _to_article_out(d)


@router.get("/articles/{keyword}/trend")
def get_keyword_trend(
    keyword: str,
    n_runs: int = Query(default=10, ge=1, le=52, description="Utolsó N futás"),
    conn: sqlite3.Connection = Depends(get_db),
) -> List[dict]:
    """Adott kulcsszó megjelenési száma az utolsó N befejezett futásban.

    Felhasználás: trend diagram a dashboardon.
    """
    return ArticleRepository(conn).trend(keyword, n_runs=n_runs)
