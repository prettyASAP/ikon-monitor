"""
/api/v1/articles endpoint tesztek.
"""
from __future__ import annotations

import pytest

from tests.conftest import insert_article, insert_run


class TestListArticles:
    def test_empty_returns_zero(self, api_client):
        resp = api_client.get("/api/v1/articles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_returns_articles(self, api_client, db_conn):
        insert_run(db_conn)
        insert_article(db_conn, article_id="a1", url="https://test.hu/a1", score=30)
        insert_article(db_conn, article_id="a2", url="https://test.hu/a2", score=10)

        resp = api_client.get("/api/v1/articles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        # score DESC sorrendben
        assert data["items"][0]["score"] == 30

    def test_filter_by_category(self, api_client, db_conn):
        insert_run(db_conn)
        insert_article(db_conn, article_id="r1", url="https://test.hu/r1", category="releváns", score=25)
        insert_article(db_conn, article_id="n1", url="https://test.hu/n1", category="zaj", score=3)

        resp = api_client.get("/api/v1/articles?category=relev%C3%A1ns")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["category"] == "releváns"

    def test_filter_by_score_min(self, api_client, db_conn):
        insert_run(db_conn)
        insert_article(db_conn, article_id="h1", url="https://test.hu/h1", score=40)
        insert_article(db_conn, article_id="l1", url="https://test.hu/l1", score=5)

        resp = api_client.get("/api/v1/articles?score_min=20")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_filter_by_run_id(self, api_client, db_conn):
        insert_run(db_conn, run_id="RA")
        insert_run(db_conn, run_id="RB")
        insert_article(db_conn, run_id="RA", article_id="ia", url="https://test.hu/ia")
        insert_article(db_conn, run_id="RB", article_id="ib", url="https://test.hu/ib")

        resp = api_client.get("/api/v1/articles?run_id=RA")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["run_id"] == "RA"

    def test_fts_search(self, api_client, db_conn):
        insert_run(db_conn)
        insert_article(
            db_conn, article_id="tv2", url="https://test.hu/tv2",
            title="TV2 rekordnézettség negyedévben",
            excerpt="A TV2 csatorna ismét listavezető",
        )
        insert_article(
            db_conn, article_id="other", url="https://test.hu/other",
            title="Más lap", excerpt="Semmi köze a TV-hez",
        )

        resp = api_client.get("/api/v1/articles?search=TV2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["article_id"] == "tv2"

    def test_pagination(self, api_client, db_conn):
        insert_run(db_conn)
        for i in range(6):
            insert_article(
                db_conn, article_id=f"pg{i}", url=f"https://test.hu/pg{i}", score=20 + i
            )

        resp = api_client.get("/api/v1/articles?limit=4&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 4
        assert data["has_more"] is True
        assert data["total"] == 6


class TestGetArticle:
    def test_get_article_not_found(self, api_client):
        resp = api_client.get("/api/v1/articles/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "NOT_FOUND"

    def test_get_article_found(self, api_client, db_conn):
        insert_run(db_conn)
        insert_article(
            db_conn, article_id="myart1", url="https://test.hu/myart1", score=42
        )

        resp = api_client.get("/api/v1/articles/myart1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["article_id"] == "myart1"
        assert data["score"] == 42


class TestKeywordTrend:
    def test_trend_returns_list(self, api_client, db_conn):
        insert_run(db_conn, run_id="TR01")
        insert_article(
            db_conn, run_id="TR01", article_id="tr1", url="https://test.hu/tr1",
            matched_keywords=["TV2"],
        )

        resp = api_client.get("/api/v1/articles/TV2/trend?n_runs=5")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(t["keyword"] == "TV2" and t["count"] == 1 for t in data)
