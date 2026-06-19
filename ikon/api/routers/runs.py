"""
Pipeline run kezelés.

POST /api/v1/runs         – aszinkron pipeline indítás (202 Accepted)
GET  /api/v1/runs         – futások listája (paginált)
GET  /api/v1/runs/{id}    – egy futás részletei
GET  /api/v1/runs/{id}/summary – kategória + forrás + kulcsszó statisztikák
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ikon.api.app import get_executor, _run_pipeline_in_thread
from ikon.api.dependencies import get_config, get_db
from ikon.api.schemas import PaginatedResponse, RunCreateRequest, RunOut, RunSummary
from ikon.config import Config
from ikon.database import Database
from ikon.models import PipelineRun
from ikon.repository import ArticleRepository, RunRepository

logger = logging.getLogger(__name__)
router = APIRouter(tags=["runs"])


def _run_to_schema(run: dict) -> RunOut:
    return RunOut(
        run_id=run.get("run_id", ""),
        status=run.get("status", "unknown"),
        started_at=run.get("started_at", ""),
        completed_at=run.get("completed_at"),
        time_window_hours=run.get("time_window_hours", 168),
        keyword_profile=run.get("keyword_profile") or "iko_ceg",
        total_raw=run.get("total_raw") or 0,
        total_unique=run.get("total_unique") or 0,
        relevant=run.get("relevant") or 0,
        review=run.get("review") or 0,
        noise=run.get("noise") or 0,
        error_msg=run.get("error_msg"),
        triggered_by=run.get("triggered_by"),
        duplicate_rate=run.get("duplicate_rate"),
    )


@router.get("/runs", response_model=PaginatedResponse[RunOut])
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    keyword_profile: Optional[str] = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> PaginatedResponse[RunOut]:
    """Pipeline futások listája (legújabb először)."""
    repo = RunRepository(conn)
    page = repo.list(limit=limit, offset=offset, status=status, keyword_profile=keyword_profile)
    return PaginatedResponse(
        items=[_run_to_schema(r) for r in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        has_more=page.has_more,
    )


@router.post("/runs", response_model=RunOut, status_code=202)
def trigger_run(
    body: RunCreateRequest,
    conn: sqlite3.Connection = Depends(get_db),
    cfg: Config = Depends(get_config),
) -> RunOut:
    """Pipeline aszinkron indítása. Visszatér azonnal (202), a státusz pollozható."""
    # 1. from_cache path validáció (path injection megelőzés)
    if body.from_cache:
        try:
            cache_path = Path(body.from_cache).resolve()
            allowed_dir = Path("output").resolve()
            if not str(cache_path).startswith(str(allowed_dir) + "/") and cache_path != allowed_dir:
                raise HTTPException(
                    status_code=400,
                    detail={"message": "from_cache csak az output/ könyvtáron belül lehet", "code": "INVALID_PATH"},
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail={"message": "Érvénytelen from_cache útvonal", "code": "INVALID_PATH"})

    # 2. Konkurens futás + run létrehozás – egyetlen lépésben a UNIQUE index véd
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    keyword_profile = body.keyword_profile
    time_window = body.time_window_hours
    model = PipelineRun(
        run_id=run_id,
        time_window_hours=time_window,
        keyword_profile=keyword_profile,
    )
    try:
        with Database(cfg.storage.db_path) as db:
            # Ellenőrzés (gyors path): ha van running, 409 előbb
            running = RunRepository(conn).get_by_status("running")
            if running:
                raise HTTPException(
                    status_code=409,
                    detail={"message": f"Pipeline már fut: {running['run_id']}", "code": "CONFLICT"},
                )
            db.create_run(model)
            import dataclasses as _dc
            snap = json.dumps(_dc.asdict(cfg.scoring), ensure_ascii=False, default=str)
            db.conn.execute(
                "UPDATE pipeline_runs SET triggered_by=?, config_snapshot=? WHERE run_id=?",
                (body.triggered_by, snap, run_id),
            )
            db.conn.commit()
    except HTTPException:
        raise
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail={"message": "Pipeline már fut", "code": "CONFLICT"},
        )

    # 3. Háttérszálon futtatás (sync endpoint → közvetlen submit, nem asyncio)
    get_executor().submit(_run_pipeline_in_thread, cfg, body.from_cache, run_id, time_window, keyword_profile)
    logger.info("Pipeline indítva (run_id=%s, time_window=%dh, profile=%s, triggered_by=%s)", run_id, time_window, keyword_profile, body.triggered_by)

    return RunOut(
        run_id=run_id,
        status="running",
        started_at=model.started_at.isoformat(),
        time_window_hours=time_window,
        keyword_profile=keyword_profile,
        triggered_by=body.triggered_by,
    )


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(
    run_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> RunOut:
    """Egy futás részletei. Státusz pollozásra használható."""
    run = RunRepository(conn).get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail={"message": f"Run nem található: {run_id}", "code": "NOT_FOUND"})
    return _run_to_schema(run)


@router.get("/runs/{run_id}/pdf")
def download_run_pdf(
    run_id: str,
    conn: sqlite3.Connection = Depends(get_db),
):
    """PDF riport letöltése: releváns cikkek (feedback-kel korrigálva)."""
    from fastapi.responses import Response as FastResponse
    from ikon.api.pdf_report import generate_run_pdf

    try:
        pdf_bytes = generate_run_pdf(conn, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc), "code": "NOT_FOUND"})
    except Exception:
        logger.exception("PDF generálási hiba (run_id=%s)", run_id)
        raise HTTPException(status_code=500, detail={"message": "PDF generálási hiba", "code": "PDF_ERROR"})

    from datetime import datetime
    import zoneinfo
    from urllib.parse import quote
    budapest_date = datetime.now(zoneinfo.ZoneInfo("Europe/Budapest")).strftime("%Y-%m-%d")
    filename = f"IKO-Sajtóelemzés-{budapest_date}.pdf"
    filename_encoded = quote(filename, safe="-_.~")
    return FastResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"IKO-Sajtoelemzes-{budapest_date}.pdf\"; filename*=UTF-8''{filename_encoded}"},
    )


@router.get("/runs/{run_id}/summary", response_model=RunSummary)
def get_run_summary(
    run_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> RunSummary:
    """Aggregált statisztikák egy futáshoz: kategória, forrás, kulcsszó bontás."""
    run = RunRepository(conn).get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail={"message": f"Run nem található: {run_id}", "code": "NOT_FOUND"})

    art_repo = ArticleRepository(conn)
    return RunSummary(
        run_id=run_id,
        category_counts=art_repo.category_counts(run_id),
        source_distribution=art_repo.source_distribution(run_id),
        keyword_stats=art_repo.keyword_stats(run_id),
    )
