"""
SQLite perzisztencia réteg.

Az adatbázis egyetlen fájl (`data/ikon.db`), amit a DS csapat közvetlenül
lekérdezhet DuckDB-vel, pandas-szal vagy bármilyen SQL klienssel.

Schema elvek:
- `pipeline_runs`: futás metaadatok (audit log)
- `raw_articles`: nyers scraping kimenet (duplikátumokkal)
- `articles`: deduplikált, pontozott egyedi cikkek
- `feedback`: emberi reviewer döntések
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from ikon.models import FeedbackDecision, FeedbackEntry, PipelineRun, RawArticle, ScoredArticle

logger = logging.getLogger(__name__)

# Migration fájlok – verziószám → SQL fájl útvonal
MIGRATIONS: dict[int, Path] = {
    2: Path(__file__).parent.parent / "migrations" / "v002_api_layer.sql",
    3: Path(__file__).parent.parent / "migrations" / "v003_fts_delete_race.sql",
    4: Path(__file__).parent.parent / "migrations" / "v004_keyword_profiles.sql",
    5: Path(__file__).parent.parent / "migrations" / "v005_cross_profile_keywords.sql",
    6: Path(__file__).parent.parent / "migrations" / "v006_tv2_hosts.sql",
}

DDL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id       TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    completed_at TEXT,
    time_window_hours INTEGER NOT NULL DEFAULT 168,
    total_raw    INTEGER DEFAULT 0,
    total_unique INTEGER DEFAULT 0,
    relevant     INTEGER DEFAULT 0,
    review       INTEGER DEFAULT 0,
    noise        INTEGER DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'running',
    error_msg    TEXT
);

CREATE TABLE IF NOT EXISTS raw_articles (
    article_id       TEXT NOT NULL,
    run_id           TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    url              TEXT NOT NULL,
    title            TEXT,
    source           TEXT,
    published_date   TEXT,
    published_time   TEXT,
    excerpt          TEXT,
    matched_keyword  TEXT NOT NULL,
    keyword_tier     TEXT NOT NULL,
    scraped_at       TEXT NOT NULL,
    PRIMARY KEY (article_id, matched_keyword, run_id)
);

CREATE TABLE IF NOT EXISTS articles (
    article_id       TEXT NOT NULL,
    run_id           TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    url              TEXT NOT NULL,
    title            TEXT,
    source           TEXT,
    source_type      TEXT,
    published_date   TEXT,
    published_time   TEXT,
    excerpt          TEXT,
    matched_keywords TEXT,   -- JSON tömb
    best_tier        TEXT,
    score            INTEGER NOT NULL,
    score_reason     TEXT,
    category         TEXT NOT NULL,
    scored_at        TEXT NOT NULL,
    PRIMARY KEY (article_id, run_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    url              TEXT PRIMARY KEY,
    decision         TEXT NOT NULL CHECK(decision IN ('releváns','nem_releváns')),
    reviewed_at      TEXT NOT NULL,
    original_score   INTEGER NOT NULL DEFAULT 0,
    reviewer_note    TEXT DEFAULT ''
);

-- Gyors lekérdezések az elemzőknek
CREATE INDEX IF NOT EXISTS idx_articles_run    ON articles(run_id);
CREATE INDEX IF NOT EXISTS idx_articles_cat    ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_score  ON articles(score DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_raw_keyword     ON raw_articles(matched_keyword);
"""


class Database:
    """SQLite adatbázis kezelő – context manager-ként használható."""

    def __init__(self, db_path: str = "data/ikon.db") -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> "Database":
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(DDL)
        self._conn.commit()
        return self

    def __exit__(self, *_) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database nincs megnyitva – használd context managerként")
        return self._conn

    def run_migrations(self) -> None:
        """Idempotens schema migration futtatás.

        Csak az alkalmazott verziószámot ellenőrzi (schema_version tábla).
        Biztonságosan futtatható minden startup-kor.
        """
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version    INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                description TEXT
            );
            INSERT OR IGNORE INTO schema_version (version, applied_at, description)
            VALUES (1, datetime('now'), 'initial DDL (retroactive)');
        """)
        applied = {
            r[0] for r in self.conn.execute("SELECT version FROM schema_version").fetchall()
        }
        for version, sql_path in sorted(MIGRATIONS.items()):
            if version not in applied:
                logger.info("Migration v%d alkalmazása: %s", version, sql_path.name)
                try:
                    self.conn.executescript(sql_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    if "duplicate column name" in str(exc).lower():
                        # Oszlop már manuálisan hozzáadva – migration jelölése kész
                        logger.warning("Migration v%d: oszlop már létezik ('%s'), migration alkalmaz.", version, exc)
                        self.conn.execute(
                            "INSERT OR IGNORE INTO schema_version (version, applied_at, description) VALUES (?, datetime('now'), ?)",
                            (version, f"auto-applied (duplicate column ignored): {sql_path.name}"),
                        )
                        self.conn.commit()
                    else:
                        logger.error("Migration v%d sikertelen: %s", version, exc)
                        raise
                logger.info("Migration v%d kész", version)

    # ------------------------------------------------------------------
    # Pipeline runs
    # ------------------------------------------------------------------

    def create_run(self, run: PipelineRun) -> None:
        self.conn.execute(
            """INSERT INTO pipeline_runs (run_id, started_at, time_window_hours, keyword_profile, status)
               VALUES (?, ?, ?, ?, ?)""",
            (run.run_id, run.started_at.isoformat(), run.time_window_hours,
             run.keyword_profile, run.status),
        )
        self.conn.commit()

    def complete_run(self, run: PipelineRun) -> None:
        self.conn.execute(
            """UPDATE pipeline_runs
               SET completed_at=?, total_raw=?, total_unique=?,
                   relevant=?, review=?, noise=?, status=?, error_msg=?
               WHERE run_id=?""",
            (
                (run.completed_at or datetime.utcnow()).isoformat(),
                run.total_raw_articles, run.total_unique_articles,
                run.relevant_count, run.review_count, run.noise_count,
                run.status, run.error_message,
                run.run_id,
            ),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Raw articles
    # ------------------------------------------------------------------

    def insert_raw_articles(self, articles: list[RawArticle], run_id: str) -> int:
        rows = [
            (
                a.article_id, run_id, a.url, a.title, a.source,
                a.published_date, a.published_time, a.excerpt,
                a.matched_keyword, a.keyword_tier, a.scraped_at.isoformat(),
            )
            for a in articles
        ]
        self.conn.executemany(
            """INSERT OR IGNORE INTO raw_articles
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self.conn.commit()
        logger.info("raw_articles: %d sor beillesztve", len(rows))
        return len(rows)

    # ------------------------------------------------------------------
    # Scored articles
    # ------------------------------------------------------------------

    @staticmethod
    def _to_iso_date(d: str) -> Optional[str]:
        if d and len(d) == 10 and d[4] == "." and d[7] == ".":
            return d.replace(".", "-")
        return None

    def insert_articles(self, articles: list[ScoredArticle], run_id: str) -> int:
        rows = [
            (
                a.article_id, run_id, a.url, a.title, a.source,
                a.source_type.value, a.published_date,
                self._to_iso_date(a.published_date),
                a.published_time, a.excerpt,
                json.dumps(a.matched_keywords, ensure_ascii=False),
                a.best_tier.value, a.score, a.score_reason,
                a.category.value, a.scored_at.isoformat(),
            )
            for a in articles
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO articles
               (article_id, run_id, url, title, source,
                source_type, published_date, published_date_iso,
                published_time, excerpt,
                matched_keywords, best_tier, score, score_reason,
                category, scored_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self.conn.commit()
        logger.info("articles: %d sor beillesztve/frissítve", len(rows))
        return len(rows)

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def upsert_feedback(self, entries: list[FeedbackEntry]) -> int:
        rows = [
            (e.url, e.decision.value, e.reviewed_at.isoformat(),
             e.original_score, e.reviewer_note)
            for e in entries
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO feedback (url, decision, reviewed_at, original_score, reviewer_note)
               VALUES (?,?,?,?,?)""",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def load_feedback(self) -> dict[str, FeedbackEntry]:
        rows = self.conn.execute("SELECT * FROM feedback").fetchall()
        return {
            row["url"]: FeedbackEntry(
                url=row["url"],
                decision=FeedbackDecision(row["decision"]),
                reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
                original_score=row["original_score"],
                reviewer_note=row["reviewer_note"] or "",
            )
            for row in rows
        }

    # ------------------------------------------------------------------
    # Elemzői lekérdezések (DS csapatnak)
    # ------------------------------------------------------------------

    def get_latest_run_id(self) -> str | None:
        row = self.conn.execute(
            "SELECT run_id FROM pipeline_runs WHERE status='completed' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return row["run_id"] if row else None

    def get_articles_for_run(self, run_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM articles WHERE run_id=? ORDER BY score DESC", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def pipeline_history(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM pipeline_runs ORDER BY started_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
