"""
Emberi reviewer feedback.

POST   /api/v1/feedback/{article_id}  – döntés rögzítése
GET    /api/v1/feedback                – összes feedback (paginált)
DELETE /api/v1/feedback/{article_id}  – döntés törlése
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ikon.api.dependencies import get_db
from ikon.api.schemas import BulkFeedbackIn, FeedbackIn, FeedbackOut, PaginatedResponse
from ikon.repository import ArticleRepository, FeedbackRepository

router = APIRouter(tags=["feedback"])


def _to_feedback_out(d: dict) -> FeedbackOut:
    return FeedbackOut(
        url=d.get("url", ""),
        decision=d.get("decision", ""),
        reviewer_id=d.get("reviewer_id"),
        reviewer_note=d.get("reviewer_note") or "",
        original_score=d.get("original_score") or 0,
        reviewed_at=d.get("reviewed_at") or "",
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
    )


@router.post("/feedback/bulk")
def submit_bulk_feedback(
    body: BulkFeedbackIn,
    run_id: Optional[str] = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Tömeges reviewer döntés rögzítése.

    Visszaad: `{success: int, errors: [{article_id, error}]}`.
    Az ismeretlen article_id-k nem dobnak hibát, csak az errors listába kerülnek.
    """
    article_repo = ArticleRepository(conn)
    feedback_repo = FeedbackRepository(conn)
    success = 0
    errors: list = []

    for item in body.items:
        art = article_repo.get(item.article_id, run_id=run_id)
        if not art:
            errors.append({"article_id": item.article_id, "error": "NOT_FOUND"})
            continue
        feedback_repo.upsert(
            url=art["url"],
            decision=item.decision,
            reviewer_id=body.reviewer_id,
            reviewer_note="",
            original_score=art.get("score") or 0,
        )
        success += 1

    return {"success": success, "errors": errors}


@router.post("/feedback/{article_id}", response_model=FeedbackOut)
def submit_feedback(
    article_id: str,
    body: FeedbackIn,
    run_id: Optional[str] = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> FeedbackOut:
    """Reviewer döntés rögzítése egy cikkhez.

    Az `article_id` az URL SHA256 hash-je (16 karakter). A `run_id` opcionális;
    ha nincs megadva, a legutóbbi futás verziójához rendeli.
    """
    art = ArticleRepository(conn).get(article_id, run_id=run_id)
    if not art:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Cikk nem található: {article_id}", "code": "NOT_FOUND"},
        )

    repo = FeedbackRepository(conn)
    result = repo.upsert(
        url=art["url"],
        decision=body.decision,
        reviewer_id=body.reviewer_id,
        reviewer_note=body.reviewer_note,
        original_score=art.get("score") or 0,
    )
    return _to_feedback_out(result)


@router.get("/feedback", response_model=PaginatedResponse[FeedbackOut])
def list_feedback(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> PaginatedResponse[FeedbackOut]:
    """Az összes rögzített reviewer döntés (legújabb először)."""
    page = FeedbackRepository(conn).list(limit=limit, offset=offset)
    return PaginatedResponse(
        items=[_to_feedback_out(d) for d in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        has_more=page.has_more,
    )


@router.delete("/feedback/{article_id}", status_code=204)
def delete_feedback(
    article_id: str,
    run_id: Optional[str] = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Reviewer döntés törlése (a cikk visszakerül az automatikus kategóriájába)."""
    art = ArticleRepository(conn).get(article_id, run_id=run_id)
    if not art:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Cikk nem található: {article_id}", "code": "NOT_FOUND"},
        )

    deleted = FeedbackRepository(conn).delete(art["url"])
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"message": "Feedback nem található ehhez a cikkhez", "code": "NOT_FOUND"},
        )
    return Response(status_code=204)
