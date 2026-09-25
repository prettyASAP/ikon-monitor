"""
Ideiglenes admin endpoint – DB backup/restore a régió-migrációhoz.
FIGYELEM: deploy után azonnal el kell távolítani!
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

router = APIRouter(tags=["admin"])

_ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")


def _check_auth(x_admin_secret: str | None) -> None:
    if not _ADMIN_SECRET or x_admin_secret != _ADMIN_SECRET:
        raise HTTPException(401, detail="Unauthorized")


def _db_path() -> Path:
    from ikon.api.dependencies import get_config
    cfg = get_config()
    return Path(cfg.storage.db_path)


@router.get("/admin/backup-db")
def backup_db(x_admin_secret: str | None = Header(default=None)) -> FileResponse:
    """A teljes SQLite adatbázis letöltése."""
    _check_auth(x_admin_secret)
    p = _db_path()
    if not p.exists():
        raise HTTPException(404, detail="DB not found")
    # WAL checkpoint: flush WAL before download
    import sqlite3
    try:
        conn = sqlite3.connect(str(p))
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        conn.close()
    except Exception:
        pass
    return FileResponse(str(p), media_type="application/octet-stream", filename="ikon.db")


@router.post("/admin/restore-db")
async def restore_db(
    file: UploadFile = File(...),
    x_admin_secret: str | None = Header(default=None),
) -> dict:
    """Feltöltött SQLite DB visszaállítása (a meglévő fájlt felülírja)."""
    _check_auth(x_admin_secret)
    p = _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    try:
        with open(tmp, "wb") as f:
            content = await file.read()
            f.write(content)
        # Ellenőrzés: valid SQLite fájl?
        import sqlite3
        conn = sqlite3.connect(str(tmp))
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.close()
        shutil.move(str(tmp), str(p))
    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        raise HTTPException(422, detail=f"Restore failed: {exc}")
    return {"ok": True, "size_bytes": p.stat().st_size}
