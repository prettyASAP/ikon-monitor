"""
Cikk lekérdezések + manuális cikk hozzáadás.

GET  /api/v1/articles              – szűrt + paginált cikk lista (FTS5 keresés)
POST /api/v1/articles              – manuális cikk hozzáadása
GET  /api/v1/articles/{article_id} – egyetlen cikk részletei
GET  /api/v1/articles/{article_id}/trend – kulcsszó trend (utolsó N futás)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ikon.api.dependencies import get_config, get_db
from ikon.api.schemas import ArticleOut, ManualArticleIn, PaginatedResponse
from ikon.repository import ArticleFilter, ArticleRepository, RunRepository, KeywordRepository

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


@router.post("/articles", response_model=ArticleOut, status_code=201)
def create_manual_article(
    body: ManualArticleIn,
    conn: sqlite3.Connection = Depends(get_db),
    cfg=Depends(get_config),
) -> ArticleOut:
    """Manuálisan felvett cikk a legutóbbi (vagy megadott) futáshoz."""
    from ikon.scoring import categorize, classify_source, score_article
    from ikon.models import Category, KeywordTier, SourceType

    if not body.url.startswith("http"):
        raise HTTPException(400, detail={"message": "Érvénytelen URL", "code": "INVALID_URL"})

    # Futás meghatározása
    run_repo = RunRepository(conn)
    if body.run_id:
        run = run_repo.get(body.run_id)
        if not run:
            raise HTTPException(404, detail={"message": "Futás nem található", "code": "NOT_FOUND"})
        run_id = body.run_id
    else:
        page = run_repo.list(limit=1, status="completed")
        if not page.items:
            raise HTTPException(409, detail={"message": "Nincs befejezett futás", "code": "NO_RUN"})
        run_id = page.items[0]["run_id"]

    # Profil → aktív kulcsszavak
    run_row = conn.execute("SELECT keyword_profile FROM pipeline_runs WHERE run_id=?", (run_id,)).fetchone()
    profile = (run_row["keyword_profile"] if run_row else None) or "iko"
    kw_rows = KeywordRepository(conn).list(active_only=True, profile=profile)

    # Kulcsszó-egyezés (case-insensitive substring)
    text = f"{body.title} {body.excerpt}".lower()
    matched = [r["keyword"] for r in kw_rows if r["keyword"].lower() in text]

    # Best tier
    tier_order = ["tier1_specifikus", "tier2_kozepes", "tier3_generikus"]
    kw_tiers = {r["keyword"]: r["tier"] for r in kw_rows}
    best_tier_val = next(
        (t for t in tier_order if any(kw_tiers.get(k) == t for k in matched)),
        "tier3_generikus",
    )

    # Scoring
    source_type = classify_source(body.source)
    score_result = score_article(matched, body.title, body.excerpt, body.source, cfg.scoring)
    category, _ = categorize(score_result.score, source_type, matched, body.title, body.excerpt, cfg.scoring)

    pub_date = body.published_date or date.today().strftime("%Y.%m.%d")
    pub_date_iso = pub_date.replace(".", "-") if pub_date else None
    article_id = hashlib.sha256(body.url.encode()).hexdigest()[:16]
    scored_at = datetime.utcnow().isoformat()

    conn.execute(
        """INSERT OR REPLACE INTO articles
           (article_id, run_id, url, title, source,
            source_type, published_date, published_date_iso,
            published_time, excerpt,
            matched_keywords, best_tier, score, score_reason,
            category, scored_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            article_id, run_id, body.url, body.title, body.source,
            source_type.value, pub_date, pub_date_iso,
            "", body.excerpt,
            json.dumps(matched, ensure_ascii=False),
            best_tier_val, score_result.score, score_result.reason,
            category.value, scored_at,
        ),
    )
    conn.commit()

    return _to_article_out({
        "article_id": article_id,
        "run_id": run_id,
        "url": body.url,
        "title": body.title,
        "source": body.source,
        "source_type": source_type.value,
        "published_date": pub_date,
        "published_date_iso": pub_date_iso,
        "published_time": "",
        "excerpt": body.excerpt,
        "matched_keywords": matched,
        "best_tier": best_tier_val,
        "score": score_result.score,
        "score_reason": score_result.reason,
        "category": category.value,
        "feedback_decision": None,
        "reviewer_id": None,
        "reviewer_note": None,
        "scored_at": scored_at,
    })


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
