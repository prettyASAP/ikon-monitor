"""
Kulcsszó kezelés.

GET    /api/v1/keywords       – kulcsszavak listája
POST   /api/v1/keywords       – új kulcsszó felvétele
PATCH  /api/v1/keywords/{id}  – aktiválás/deaktiválás/tier-csere
DELETE /api/v1/keywords/{id}  – törlés (hard delete)
GET    /api/v1/config/scoring – jelenlegi scoring konfiguráció
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ikon.api.dependencies import get_config, get_db
from ikon.api.schemas import KeywordIn, KeywordOut, KeywordPatch, ScoringConfigOut
from ikon.config import Config
from ikon.repository import KeywordRepository

router = APIRouter(tags=["keywords"])


def _to_keyword_out(d: dict) -> KeywordOut:
    return KeywordOut(
        id=d["id"],
        keyword=d["keyword"],
        tier=d["tier"],
        is_active=bool(d["is_active"]),
        profile=d.get("profile") or "iko_ceg",
        created_at=d.get("created_at") or "",
        updated_at=d.get("updated_at") or "",
    )


@router.get("/keywords", response_model=List[KeywordOut])
def list_keywords(
    tier: Optional[str] = Query(default=None, description="Szűrés tier szerint"),
    active_only: bool = Query(default=False, description="Csak aktív kulcsszavak"),
    profile: Optional[str] = Query(default=None, description="Kulcsszó profil: iko_ceg | tv_radio_musorok"),
    conn: sqlite3.Connection = Depends(get_db),
) -> List[KeywordOut]:
    """Összes kulcsszó tierrel és aktiváltsági státusszal."""
    rows = KeywordRepository(conn).list(tier=tier, active_only=active_only, profile=profile)
    return [_to_keyword_out(r) for r in rows]


@router.post("/keywords", response_model=KeywordOut, status_code=201)
def create_keyword(
    body: KeywordIn,
    conn: sqlite3.Connection = Depends(get_db),
) -> KeywordOut:
    """Új kulcsszó felvétele. A következő pipeline futástól aktív."""
    try:
        row = KeywordRepository(conn).create(keyword=body.keyword, tier=body.tier, profile=body.profile)
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(
                status_code=409,
                detail={"message": f"Kulcsszó már létezik: '{body.keyword}'", "code": "CONFLICT"},
            )
        raise
    return _to_keyword_out(row)


@router.patch("/keywords/{keyword_id}", response_model=KeywordOut)
def patch_keyword(
    keyword_id: int,
    body: KeywordPatch,
    conn: sqlite3.Connection = Depends(get_db),
) -> KeywordOut:
    """Kulcsszó aktiválása/deaktiválása vagy tier-csere.

    Deaktivált kulcsszóra (`is_active=false`) a scraper nem keres a következő futástól.
    """
    row = KeywordRepository(conn).update(
        keyword_id=keyword_id,
        is_active=body.is_active,
        tier=body.tier,
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Kulcsszó nem található: {keyword_id}", "code": "NOT_FOUND"},
        )
    return _to_keyword_out(row)


@router.delete("/keywords/{keyword_id}", status_code=204)
def delete_keyword(
    keyword_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Kulcsszó törlése (hard delete). Ajánlott inkább PATCH is_active=false."""
    deleted = KeywordRepository(conn).delete(keyword_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Kulcsszó nem található: {keyword_id}", "code": "NOT_FOUND"},
        )
    return Response(status_code=204)


@router.get("/config/scoring", response_model=ScoringConfigOut, tags=["config"])
def get_scoring_config(cfg: Config = Depends(get_config)) -> ScoringConfigOut:
    """Jelenlegi scoring konfiguráció (config/settings.yaml-ból)."""
    s = cfg.scoring
    return ScoringConfigOut(
        tier1_base_score=s.tier1_base_score,
        tier2_base_score=s.tier2_base_score,
        tier3_base_score=s.tier3_base_score,
        false_positive_penalty=s.false_positive_penalty,
        context_bonus_per_word=s.context_bonus_per_word,
        context_bonus_cap=s.context_bonus_cap,
        bulvar_tier3_penalty=s.bulvar_tier3_penalty,
        threshold_relevant=s.thresholds.relevant,
        threshold_review=s.thresholds.review,
    )
