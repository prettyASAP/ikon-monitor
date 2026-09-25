"""
FastAPI alkalmazás factory.

Futtatás:
    uvicorn ikon.api.app:app --reload --port 8000

A lifespan hook:
    1. Idempotens schema migration (v002)
    2. Keyword seeding (ha üres a keywords tábla)
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ikon.config import Config, load_config
from ikon.database import Database
from ikon.models import PipelineRun

logger = logging.getLogger(__name__)

# Lifespan hozza létre és zárja be – így tesztenként friss executor keletkezik
_executor: Optional[ThreadPoolExecutor] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: executor init + migration + keyword seed. Shutdown: executor bezárása."""
    global _executor
    _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ikon-pipeline")

    cfg = load_config()
    with Database(cfg.storage.db_path) as db:
        db.run_migrations()
        from ikon.repository import KeywordRepository
        seeded = KeywordRepository(db.conn).seed_from_python()
        if seeded:
            logger.info("Keywords seeded az adatbázisba: %d kulcsszó", seeded)
        # Szerver újraindítás után az árva 'running' futásokat lezárjuk
        orphaned = db.conn.execute(
            "SELECT run_id FROM pipeline_runs WHERE status = 'running'"
        ).fetchall()
        for row in orphaned:
            db.conn.execute(
                "UPDATE pipeline_runs SET status='failed', completed_at=datetime('now'),"
                " error_msg='Pipeline megszakadt (szerver újraindult)' WHERE run_id=?",
                (row[0],),
            )
        if orphaned:
            db.conn.commit()
            logger.warning("Árva futások lezárva: %s", [r[0] for r in orphaned])
    # Embedding modell előtöltése (5-6s disk cache-ből, első futásnál letöltés ~470 MB)
    try:
        from ikon.embedder import _get_model
        _get_model()
        logger.info("Embedding modell betöltve")
    except Exception:
        logger.warning("Embedding modell betöltése sikertelen – rescue step ki lesz hagyva", exc_info=True)

    logger.info("IKO Monitor API elindult (db: %s)", cfg.storage.db_path)
    yield
    _executor.shutdown(wait=False)
    _executor = None
    logger.info("IKO Monitor API leállt")


def create_app() -> FastAPI:
    app = FastAPI(
        title="IKO Monitor API",
        description="Média monitoring pipeline REST backend – IKO Műsorgyártó",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:4173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from ikon.api.routers import articles, feedback, health, keywords, runs

    app.include_router(health.router)
    app.include_router(runs.router, prefix="/api/v1")
    app.include_router(articles.router, prefix="/api/v1")
    app.include_router(feedback.router, prefix="/api/v1")
    app.include_router(keywords.router, prefix="/api/v1")

    # Statikus frontend serving (production: Dockerfile buildeli be)
    _dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if _dist.exists():
        app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")

    return app


# ---------------------------------------------------------------------------
# Pipeline háttér futtatás
# ---------------------------------------------------------------------------

def _run_pipeline_in_thread(
    cfg: Config,
    from_cache: Optional[str],
    run_id: str,
    time_window_hours: int = 168,
    keyword_profile: str = "iko_ceg",
) -> None:
    """Szinkron függvény a ThreadPoolExecutor-ban fut.

    A run_id-t a caller már létrehozta és a DB-be írta 'running' státusszal.
    A pipeline ebből indul ki és maga frissíti a státuszt.
    """
    import sqlite3 as _sqlite3
    from ikon.repository import KeywordRepository
    from ikon.pipeline import run_pipeline

    try:
        # Aktív kulcsszavak betöltése DB-ből (profil szerinti szűréssel)
        conn = _sqlite3.connect(str(Database(cfg.storage.db_path).path))
        conn.row_factory = _sqlite3.Row
        try:
            active_keywords = KeywordRepository(conn).get_active_keywords(profile=keyword_profile)
        finally:
            conn.close()

        import dataclasses as _dc
        effective_cfg = _dc.replace(
            cfg,
            scraping=_dc.replace(cfg.scraping, time_window_hours=time_window_hours),
        )
        run_pipeline(
            effective_cfg,
            from_cache=Path(from_cache) if from_cache else None,
            keywords=active_keywords if active_keywords else None,
            run_id=run_id,
        )
    except Exception:
        logger.exception("Pipeline thread hiba (run_id=%s)", run_id)
        import sqlite3 as _sq
        try:
            _c = _sq.connect(str(Database(cfg.storage.db_path).path))
            _c.execute(
                "UPDATE pipeline_runs SET status='failed', completed_at=datetime('now'),"
                " error_msg='Belső hiba a pipeline futásban' WHERE run_id=? AND status='running'",
                (run_id,),
            )
            _c.commit()
            _c.close()
        except Exception:
            pass


def get_executor() -> ThreadPoolExecutor:
    if _executor is None:
        raise RuntimeError("Executor not initialized – lifespan not started?")
    return _executor


# Alkalmazás példány (uvicorn által importálva)
app = create_app()
