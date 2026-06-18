"""
FastAPI Dependency Injection.

Minden router `Depends(get_db)` hívással kap sqlite3.Connection-t.
A kapcsolat kérés végén automatikusan bezárul.
"""
from __future__ import annotations

import sqlite3
from typing import Generator

from fastapi import Depends

from ikon.config import Config, load_config
from ikon.database import Database


from functools import lru_cache as _lru_cache

@_lru_cache(maxsize=1)
def _cached_config() -> Config:
    return load_config()

def get_config() -> Config:
    return _cached_config()


def get_db(cfg: Config = Depends(get_config)) -> Generator[sqlite3.Connection, None, None]:
    """Yields egy sqlite3 connection-t. WAL mode, 5 másodperces busy timeout."""
    db = Database(cfg.storage.db_path)
    conn = sqlite3.connect(str(db.path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")  # pipeline írás alatt sem blockol
    try:
        yield conn
    finally:
        conn.close()
