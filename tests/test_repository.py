"""
Repository réteg tesztek.

Minden teszt in-process SQLite-ot használ (db_conn fixture, WAL nélkül
sem probléma mert 1 kapcsolat).
"""
from __future__ import annotations

import json

import pytest

from ikon.keywords import ALL_KEYWORDS
from ikon.repository import ArticleFilter, ArticleRepository, KeywordRepository, RunRepository

from tests.conftest import insert_article, insert_run


# ---------------------------------------------------------------------------
# KeywordRepository
# ---------------------------------------------------------------------------

class TestKeywordSeed:
    def test_seed_inserts_all_python_keywords(self, db_conn):
        repo = KeywordRepository(db_conn)
        repo.seed_from_python()
        # v005 migration pre-seed-eli a 15 NAPI kulcsszót; seed_from_python
        # INSERT OR IGNORE-t használ, ezért a total DB count == len(ALL_KEYWORDS).
        total = db_conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
        assert total == len(ALL_KEYWORDS)

    def test_seed_is_idempotent(self, db_conn):
        repo = KeywordRepository(db_conn)
        repo.seed_from_python()
        second = repo.seed_from_python()
        assert second == 0

    def test_get_active_keywords_returns_all_after_seed(self, db_conn):
        from ikon.keywords import KEYWORDS
        repo = KeywordRepository(db_conn)
        repo.seed_from_python()
        # get_active_keywords() default: iko_ceg profil
        active = repo.get_active_keywords(profile="iko_ceg")
        iko_count = sum(len(kws) for kws in KEYWORDS.values())
        assert len(active) == iko_count

    def test_list_filter_by_tier(self, db_conn):
        repo = KeywordRepository(db_conn)
        repo.seed_from_python()
        tier1 = repo.list(tier="tier1_specifikus")
        assert all(kw["tier"] == "tier1_specifikus" for kw in tier1)
        assert len(tier1) > 0

    def test_create_and_update_keyword(self, db_conn):
        repo = KeywordRepository(db_conn)
        row = repo.create("TesztKulcsszó", "tier2_kozepes")
        assert row["keyword"] == "TesztKulcsszó"
        assert row["is_active"] == 1

        updated = repo.update(row["id"], is_active=False)
        assert updated["is_active"] == 0

    def test_delete_keyword(self, db_conn):
        repo = KeywordRepository(db_conn)
        row = repo.create("TörlendőSzó", "tier3_generikus")
        assert repo.delete(row["id"]) is True
        assert repo.delete(row["id"]) is False


# ---------------------------------------------------------------------------
# ArticleRepository – szűrés
# ---------------------------------------------------------------------------

class TestArticleFilter:
    def test_list_empty_returns_zero(self, db_conn):
        page = ArticleRepository(db_conn).list(ArticleFilter())
        assert page.total == 0
        assert page.items == []

    def test_filter_by_category(self, db_conn):
        insert_run(db_conn)
        insert_article(db_conn, article_id="a1", url="https://test.hu/a1", category="releváns", score=25)
        insert_article(db_conn, article_id="a2", url="https://test.hu/a2", category="zaj", score=3)

        page = ArticleRepository(db_conn).list(ArticleFilter(category="releváns"))
        assert page.total == 1
        assert page.items[0]["category"] == "releváns"

    def test_filter_by_score_min(self, db_conn):
        insert_run(db_conn)
        insert_article(db_conn, article_id="s1", url="https://test.hu/s1", score=40)
        insert_article(db_conn, article_id="s2", url="https://test.hu/s2", score=5)

        page = ArticleRepository(db_conn).list(ArticleFilter(score_min=20))
        assert page.total == 1
        assert page.items[0]["score"] == 40

    def test_filter_by_run_id(self, db_conn):
        insert_run(db_conn, run_id="RUN_A")
        insert_run(db_conn, run_id="RUN_B")
        insert_article(db_conn, run_id="RUN_A", article_id="x1", url="https://t.hu/x1")
        insert_article(db_conn, run_id="RUN_B", article_id="x2", url="https://t.hu/x2")

        page = ArticleRepository(db_conn).list(ArticleFilter(run_id="RUN_A"))
        assert page.total == 1
        assert page.items[0]["run_id"] == "RUN_A"

    def test_pagination(self, db_conn):
        insert_run(db_conn)
        for i in range(5):
            insert_article(
                db_conn,
                article_id=f"p{i}",
                url=f"https://test.hu/p{i}",
                score=10 + i,
            )

        page = ArticleRepository(db_conn).list(ArticleFilter(limit=2, offset=0))
        assert len(page.items) == 2
        assert page.total == 5
        assert page.has_more is True

        page2 = ArticleRepository(db_conn).list(ArticleFilter(limit=2, offset=4))
        assert len(page2.items) == 1
        assert page2.has_more is False

    def test_filter_by_date_range(self, db_conn):
        insert_run(db_conn)
        insert_article(db_conn, article_id="d1", url="https://test.hu/d1", published_date_iso="2026-06-10")
        insert_article(db_conn, article_id="d2", url="https://test.hu/d2", published_date_iso="2026-06-20")

        page = ArticleRepository(db_conn).list(
            ArticleFilter(date_from="2026-06-15", date_to="2026-06-30")
        )
        assert page.total == 1
        assert page.items[0]["published_date_iso"] == "2026-06-20"

    def test_get_article_returns_latest_by_default(self, db_conn):
        insert_run(db_conn, run_id="R1")
        insert_run(db_conn, run_id="R2")
        # same article_id, two runs
        insert_article(db_conn, run_id="R1", article_id="same", url="https://test.hu/same", score=10)
        insert_article(db_conn, run_id="R2", article_id="same", url="https://test.hu/same", score=15)

        result = ArticleRepository(db_conn).get("same")
        # legfrissebb futás (scored_at szerint DESC)
        assert result is not None

    def test_get_article_with_run_id(self, db_conn):
        insert_run(db_conn, run_id="R1")
        insert_article(db_conn, run_id="R1", article_id="z1", url="https://test.hu/z1", score=99)

        result = ArticleRepository(db_conn).get("z1", run_id="R1")
        assert result is not None
        assert result["score"] == 99

    def test_get_article_not_found(self, db_conn):
        result = ArticleRepository(db_conn).get("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# ArticleRepository – FTS5
# ---------------------------------------------------------------------------

class TestFTS:
    def test_fts_search_returns_matching_articles(self, db_conn):
        insert_run(db_conn)
        insert_article(
            db_conn, article_id="tv2art", url="https://test.hu/tv2",
            title="TV2 rekordnézettség", excerpt="A TV2 csatorna jól teljesített",
        )
        insert_article(
            db_conn, article_id="other", url="https://test.hu/other",
            title="Más cikk", excerpt="Nincs semmi köze a TV-hez",
        )

        page = ArticleRepository(db_conn).list(ArticleFilter(search="TV2"))
        assert page.total == 1
        assert page.items[0]["article_id"] == "tv2art"

    def test_fts_search_no_match_returns_empty(self, db_conn):
        insert_run(db_conn)
        insert_article(db_conn, article_id="x1", url="https://test.hu/x1", title="Semmi")

        page = ArticleRepository(db_conn).list(ArticleFilter(search="KizárólagEzNincsItt"))
        assert page.total == 0


# ---------------------------------------------------------------------------
# ArticleRepository – aggregáció
# ---------------------------------------------------------------------------

class TestAggregation:
    def test_category_counts(self, db_conn):
        insert_run(db_conn)
        insert_article(db_conn, article_id="c1", url="https://test.hu/c1", category="releváns", score=25)
        insert_article(db_conn, article_id="c2", url="https://test.hu/c2", category="releváns", score=22)
        insert_article(db_conn, article_id="c3", url="https://test.hu/c3", category="zaj", score=2)

        counts = ArticleRepository(db_conn).category_counts("RUN001")
        assert counts["releváns"] == 2
        assert counts["zaj"] == 1

    def test_source_distribution(self, db_conn):
        insert_run(db_conn)
        insert_article(db_conn, article_id="m1", url="https://test.hu/m1", source="Media1")
        insert_article(db_conn, article_id="m2", url="https://test.hu/m2", source="Media1")
        insert_article(db_conn, article_id="m3", url="https://test.hu/m3", source="HVG")

        dist = ArticleRepository(db_conn).source_distribution("RUN001")
        sources = {d["source"]: d["cnt"] for d in dist}
        assert sources["Media1"] == 2
        assert sources["HVG"] == 1

    def test_keyword_stats(self, db_conn):
        insert_run(db_conn)
        insert_article(
            db_conn, article_id="k1", url="https://test.hu/k1",
            matched_keywords=["IKO Műsorgyártó", "TV2"], category="releváns",
        )
        insert_article(
            db_conn, article_id="k2", url="https://test.hu/k2",
            matched_keywords=["TV2"], category="zaj",
        )

        stats = ArticleRepository(db_conn).keyword_stats("RUN001")
        kw_map = {s["keyword"]: s for s in stats}

        assert kw_map["TV2"]["count"] == 2
        assert kw_map["TV2"]["relevant_count"] == 1
        assert kw_map["IKO Műsorgyártó"]["count"] == 1

    def test_trend_returns_chronological_list(self, db_conn):
        for i in range(3):
            rid = f"RUNX{i}"
            insert_run(db_conn, run_id=rid)
            insert_article(
                db_conn, run_id=rid, article_id=f"t{i}", url=f"https://test.hu/t{i}",
                matched_keywords=["TV2"],
            )

        trend = ArticleRepository(db_conn).trend("TV2", n_runs=10)
        assert len(trend) == 3
        assert all("run_id" in t and "count" in t for t in trend)
        assert all(t["count"] == 1 for t in trend)


# ---------------------------------------------------------------------------
# RunRepository
# ---------------------------------------------------------------------------

class TestRunRepository:
    def test_list_runs_empty(self, db_conn):
        page = RunRepository(db_conn).list()
        assert page.total == 0

    def test_get_by_status(self, db_conn):
        insert_run(db_conn, run_id="RUNNING_RUN", status="running")
        insert_run(db_conn, run_id="DONE_RUN", status="completed")

        running = RunRepository(db_conn).get_by_status("running")
        assert running is not None
        assert running["run_id"] == "RUNNING_RUN"

    def test_schema_version_returns_integer(self, db_conn):
        version = RunRepository(db_conn).schema_version()
        assert isinstance(version, int)
        assert version >= 2
