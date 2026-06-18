"""
Repository réteg – typed query abstraction az API routerek számára.

Tervezési elvek:
- Minden metódus sqlite3.Connection-t kap paraméterül (nem kezel saját kapcsolatot).
- A pipeline ikon/database.py-t használja íráshoz; az API a get_db() dependency-ből
  kap connection-t olvasáshoz. A WAL mode mindkét irányban biztonságos.
- A return típus mindig dict (sqlite3.Row-ból konvertálva), hogy a FastAPI
  routers bármilyen Pydantic modellbe tudják deserializálni.

Importálás (API routerből):
    from ikon.repository import ArticleRepository, ArticleFilter, Page
    repo = ArticleRepository(conn)
    page = repo.list(ArticleFilter(category="releváns", limit=50))
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Generikus paginator
# ---------------------------------------------------------------------------

@dataclass
class Page(Generic[T]):
    """Pagináció boríték a listás endpoint válaszokhoz."""
    items: List[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + self.limit < self.total


# ---------------------------------------------------------------------------
# ArticleRepository
# ---------------------------------------------------------------------------

@dataclass
class ArticleFilter:
    """Összes szűrhető mező a /api/v1/articles endpoint-hoz."""
    run_id: Optional[str] = None
    category: Optional[str] = None          # 'releváns'|'felülvizsgálandó'|'zaj'
    source_type: Optional[str] = None       # 'médiaipari'|'bulvár'|'egyéb'
    best_tier: Optional[str] = None         # 'tier1_specifikus'|...
    score_min: Optional[int] = None
    score_max: Optional[int] = None
    date_from: Optional[str] = None         # YYYY-MM-DD (published_date_iso)
    date_to: Optional[str] = None           # YYYY-MM-DD
    search: Optional[str] = None            # FTS5 keresési lekérdezés
    has_feedback: Optional[bool] = None     # True = csak reviewer által jelölt cikkek
    limit: int = 50
    offset: int = 0


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    # JSON mezők deserializálása
    if isinstance(d.get("matched_keywords"), str):
        try:
            d["matched_keywords"] = json.loads(d["matched_keywords"])
        except (json.JSONDecodeError, TypeError):
            d["matched_keywords"] = []
    return d


class ArticleRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list(self, f: ArticleFilter) -> Page[dict]:
        """Szűrt + paginált cikkek listája. FTS5-öt használ ha f.search van."""
        params: list = []
        where: list[str] = []

        if f.search:
            # FTS5 keresés a virtuális táblán keresztül
            base_from = """
                FROM articles a
                JOIN articles_fts fts ON a.rowid = fts.rowid
                LEFT JOIN feedback fb ON a.url = fb.url
            """
            where.append("articles_fts MATCH ?")
            params.append(f.search)
        else:
            base_from = """
                FROM articles a
                LEFT JOIN feedback fb ON a.url = fb.url
            """

        if f.run_id:
            where.append("a.run_id = ?")
            params.append(f.run_id)
        if f.category:
            where.append("a.category = ?")
            params.append(f.category)
        if f.source_type:
            where.append("a.source_type = ?")
            params.append(f.source_type)
        if f.best_tier:
            where.append("a.best_tier = ?")
            params.append(f.best_tier)
        if f.score_min is not None:
            where.append("a.score >= ?")
            params.append(f.score_min)
        if f.score_max is not None:
            where.append("a.score <= ?")
            params.append(f.score_max)
        if f.date_from:
            where.append("a.published_date_iso >= ?")
            params.append(f.date_from)
        if f.date_to:
            where.append("a.published_date_iso <= ?")
            params.append(f.date_to)
        if f.has_feedback is True:
            where.append("fb.url IS NOT NULL")
        elif f.has_feedback is False:
            where.append("fb.url IS NULL")

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        count_sql = f"SELECT COUNT(*) {base_from} {where_sql}"
        total = self._conn.execute(count_sql, params).fetchone()[0]

        select_sql = f"""
            SELECT a.*, fb.decision AS feedback_decision,
                   fb.reviewer_id, fb.reviewer_note
            {base_from}
            {where_sql}
            ORDER BY a.score DESC, a.published_date_iso DESC
            LIMIT ? OFFSET ?
        """
        rows = self._conn.execute(select_sql, params + [f.limit, f.offset]).fetchall()
        return Page(
            items=[_row_to_dict(r) for r in rows],
            total=total,
            limit=f.limit,
            offset=f.offset,
        )

    def get(self, article_id: str, run_id: Optional[str] = None) -> Optional[dict]:
        """Visszaadja az article-t. Ha run_id None, a legutóbbi futás verzióját adja."""
        if run_id:
            sql = """
                SELECT a.*, fb.decision AS feedback_decision,
                       fb.reviewer_id, fb.reviewer_note
                FROM articles a LEFT JOIN feedback fb ON a.url = fb.url
                WHERE a.article_id = ? AND a.run_id = ?
            """
            row = self._conn.execute(sql, (article_id, run_id)).fetchone()
        else:
            sql = """
                SELECT a.*, fb.decision AS feedback_decision,
                       fb.reviewer_id, fb.reviewer_note
                FROM articles a LEFT JOIN feedback fb ON a.url = fb.url
                WHERE a.article_id = ?
                ORDER BY a.scored_at DESC
                LIMIT 1
            """
            row = self._conn.execute(sql, (article_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def category_counts(self, run_id: str) -> dict:
        rows = self._conn.execute(
            "SELECT category, COUNT(*) AS cnt FROM articles WHERE run_id = ? GROUP BY category",
            (run_id,),
        ).fetchall()
        return {r["category"]: r["cnt"] for r in rows}

    def source_distribution(self, run_id: str, limit: int = 15) -> List[dict]:
        rows = self._conn.execute(
            """SELECT source, source_type, COUNT(*) AS cnt
               FROM articles WHERE run_id = ?
               GROUP BY source ORDER BY cnt DESC LIMIT ?""",
            (run_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def keyword_stats(self, run_id: str) -> List[dict]:
        """Kulcsszó-szintű statisztika (matched_keywords JSON tömb alapján)."""
        rows = self._conn.execute(
            "SELECT matched_keywords, best_tier, category FROM articles WHERE run_id = ?",
            (run_id,),
        ).fetchall()

        stats: dict[str, dict] = {}
        for row in rows:
            try:
                kws = json.loads(row["matched_keywords"] or "[]")
            except (json.JSONDecodeError, TypeError):
                kws = []
            for kw in kws:
                if kw not in stats:
                    stats[kw] = {"keyword": kw, "tier": row["best_tier"], "count": 0, "relevant_count": 0}
                stats[kw]["count"] += 1
                if row["category"] == "releváns":
                    stats[kw]["relevant_count"] += 1

        return sorted(stats.values(), key=lambda x: x["count"], reverse=True)

    def trend(self, keyword: str, n_runs: int = 10) -> List[dict]:
        """Adott kulcsszó megjelenési trendje az utolsó N befejezett futásban."""
        runs = self._conn.execute(
            """SELECT run_id, started_at FROM pipeline_runs
               WHERE status = 'completed'
               ORDER BY started_at DESC LIMIT ?""",
            (n_runs,),
        ).fetchall()

        result = []
        for run in reversed(runs):  # kronológiai sorrend
            count = self._conn.execute(
                """SELECT COUNT(DISTINCT a.article_id)
                   FROM articles a, json_each(a.matched_keywords) kw
                   WHERE a.run_id = ? AND kw.value = ?""",
                (run["run_id"], keyword),
            ).fetchone()[0]
            result.append({
                "run_id": run["run_id"],
                "started_at": run["started_at"],
                "count": count,
                "keyword": keyword,
            })
        return result


# ---------------------------------------------------------------------------
# RunRepository
# ---------------------------------------------------------------------------

class RunRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list(
        self,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None,
        keyword_profile: Optional[str] = None,
    ) -> Page[dict]:
        where_parts = []
        params_where: list = []
        if status:
            where_parts.append("status = ?")
            params_where.append(status)
        if keyword_profile:
            where_parts.append("COALESCE(keyword_profile, 'iko_ceg') = ?")
            params_where.append(keyword_profile)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        params: list = params_where + [limit, offset]
        total = self._conn.execute(
            f"SELECT COUNT(*) FROM pipeline_runs {where}",
            params_where,
        ).fetchone()[0]
        rows = self._conn.execute(
            f"SELECT * FROM pipeline_runs {where} ORDER BY started_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            if d.get("total_raw") and d.get("total_unique"):
                d["duplicate_rate"] = round(1 - d["total_unique"] / d["total_raw"], 3)
            else:
                d["duplicate_rate"] = None
            items.append(d)
        return Page(items=items, total=total, limit=limit, offset=offset)

    def get(self, run_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("total_raw") and d.get("total_unique"):
            d["duplicate_rate"] = round(1 - d["total_unique"] / d["total_raw"], 3)
        return d

    def get_by_status(self, status: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM pipeline_runs WHERE status = ? ORDER BY started_at DESC LIMIT 1",
            (status,),
        ).fetchone()
        return dict(row) if row else None

    def get_latest_completed(self) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM pipeline_runs WHERE status = 'completed' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def schema_version(self) -> int:
        try:
            row = self._conn.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()
            return row[0] or 1
        except sqlite3.OperationalError:
            return 1


# ---------------------------------------------------------------------------
# FeedbackRepository
# ---------------------------------------------------------------------------

class FeedbackRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(
        self,
        url: str,
        decision: str,
        reviewer_id: Optional[str],
        reviewer_note: str,
        original_score: int,
    ) -> dict:
        now = _now_iso()
        existing = self.get_by_url(url)
        if existing:
            self._conn.execute(
                """UPDATE feedback
                   SET decision=?, reviewer_id=?, reviewer_note=?,
                       reviewed_at=?, updated_at=?
                   WHERE url=?""",
                (decision, reviewer_id, reviewer_note, now, now, url),
            )
        else:
            self._conn.execute(
                """INSERT INTO feedback
                   (url, decision, reviewed_at, original_score, reviewer_note,
                    reviewer_id, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (url, decision, now, original_score, reviewer_note,
                 reviewer_id, now, now),
            )
        self._conn.commit()
        return self.get_by_url(url)  # type: ignore[return-value]

    def get_by_url(self, url: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM feedback WHERE url = ?", (url,)
        ).fetchone()
        return dict(row) if row else None

    def delete(self, url: str) -> bool:
        cursor = self._conn.execute("DELETE FROM feedback WHERE url = ?", (url,))
        self._conn.commit()
        return cursor.rowcount > 0

    def list(self, limit: int = 100, offset: int = 0) -> Page[dict]:
        total = self._conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        rows = self._conn.execute(
            "SELECT * FROM feedback ORDER BY reviewed_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return Page(
            items=[dict(r) for r in rows],
            total=total, limit=limit, offset=offset,
        )


# ---------------------------------------------------------------------------
# KeywordRepository
# ---------------------------------------------------------------------------

class KeywordRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def seed_from_python(self) -> int:
        """Idempotens seed: INSERT OR IGNORE minden profilhoz.

        Minden startup-kor biztonságosan futtatható: meglévő sorok változatlanok,
        hiányzó kulcsszavak (pl. újonnan hozzáadottak) automatikusan pótlódnak.
        Returns: összes beillesztett sor száma
        """
        from ikon.keywords import KEYWORDS, TV_RADIO_KEYWORDS, HTEN_KEYWORDS, NAPI_KEYWORDS

        profiles_data = [
            ("iko_ceg",          KEYWORDS),
            ("tv_radio_musorok", TV_RADIO_KEYWORDS),
            ("hten",             HTEN_KEYWORDS),
            ("napi",             NAPI_KEYWORDS),
        ]
        inserted = 0
        for profile_name, kw_dict in profiles_data:
            before = self._conn.execute(
                "SELECT COUNT(*) FROM keywords WHERE profile = ?", (profile_name,)
            ).fetchone()[0]
            rows = [(kw, tier, profile_name) for tier, kws in kw_dict.items() for kw in kws]
            self._conn.executemany(
                "INSERT OR IGNORE INTO keywords (keyword, tier, profile) VALUES (?, ?, ?)", rows
            )
            self._conn.commit()
            after = self._conn.execute(
                "SELECT COUNT(*) FROM keywords WHERE profile = ?", (profile_name,)
            ).fetchone()[0]
            n = after - before
            if n > 0:
                logger.info("%s kulcsszavak seedelve: %d db", profile_name, n)
            inserted += n
        return inserted

    def get_active_keywords(self, profile: str = "iko_ceg") -> List[str]:
        """A pipeline-nak: csak aktív kulcsszavak adott profilhoz (tier prioritás)."""
        rows = self._conn.execute(
            """SELECT keyword FROM keywords
               WHERE is_active = 1 AND COALESCE(profile, 'iko_ceg') = ?
               ORDER BY
                 CASE tier
                   WHEN 'tier1_specifikus' THEN 1
                   WHEN 'tier2_kozepes'    THEN 2
                   ELSE 3
                 END,
                 keyword""",
            (profile,),
        ).fetchall()
        return [r["keyword"] for r in rows]

    def list(
        self,
        tier: Optional[str] = None,
        active_only: bool = False,
        profile: Optional[str] = None,
    ) -> List[dict]:
        where_parts = []
        params: list = []
        if tier:
            where_parts.append("tier = ?")
            params.append(tier)
        if active_only:
            where_parts.append("is_active = 1")
        if profile:
            where_parts.append("COALESCE(profile, 'iko_ceg') = ?")
            params.append(profile)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        rows = self._conn.execute(
            f"SELECT * FROM keywords {where} ORDER BY tier, keyword", params
        ).fetchall()
        return [dict(r) for r in rows]

    def create(self, keyword: str, tier: str, profile: str = "iko_ceg") -> dict:
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO keywords (keyword, tier, profile, created_at, updated_at) VALUES (?,?,?,?,?)",
            (keyword, tier, profile, now, now),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM keywords WHERE keyword = ? AND COALESCE(profile, 'iko_ceg') = ?",
            (keyword, profile),
        ).fetchone()
        return dict(row)

    def update(
        self,
        keyword_id: int,
        is_active: Optional[bool] = None,
        tier: Optional[str] = None,
    ) -> Optional[dict]:
        sets: list[str] = ["updated_at = ?"]
        params: list = [_now_iso()]
        if is_active is not None:
            sets.append("is_active = ?")
            params.append(1 if is_active else 0)
        if tier is not None:
            sets.append("tier = ?")
            params.append(tier)
        params.append(keyword_id)
        self._conn.execute(
            f"UPDATE keywords SET {', '.join(sets)} WHERE id = ?", params
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM keywords WHERE id = ?", (keyword_id,)
        ).fetchone()
        return dict(row) if row else None

    def delete(self, keyword_id: int) -> bool:
        cursor = self._conn.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
        self._conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat()
