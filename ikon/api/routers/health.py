from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ikon.api.dependencies import get_config, get_db
from ikon.api.schemas import HealthOut
from ikon.config import Config
from ikon.repository import RunRepository

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health_check(
    conn: sqlite3.Connection = Depends(get_db),
    cfg: Config = Depends(get_config),
) -> HealthOut:
    """Szerver és adatbázis állapot ellenőrzése."""
    try:
        schema_v = RunRepository(conn).schema_version()
        db_status = "connected"
    except Exception:
        schema_v = 0
        db_status = "error"

    return HealthOut(status="ok", db=db_status, schema_version=schema_v)
