"""
/api/v1/runs endpoint tesztek.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.conftest import insert_run


class TestGetRuns:
    def test_list_runs_empty(self, api_client):
        resp = api_client.get("/api/v1/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_runs_returns_paginated(self, api_client, db_conn):
        insert_run(db_conn, run_id="R1")
        insert_run(db_conn, run_id="R2")

        resp = api_client.get("/api/v1/runs?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 1
        assert data["has_more"] is True

    def test_get_single_run(self, api_client, db_conn):
        insert_run(db_conn, run_id="MYRUN01")

        resp = api_client.get("/api/v1/runs/MYRUN01")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == "MYRUN01"

    def test_get_run_not_found(self, api_client):
        resp = api_client.get("/api/v1/runs/NOPE")
        assert resp.status_code == 404

    def test_list_runs_filter_by_status(self, api_client, db_conn):
        insert_run(db_conn, run_id="COMP01", status="completed")
        insert_run(db_conn, run_id="FAIL01", status="failed")

        resp = api_client.get("/api/v1/runs?status=completed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["run_id"] == "COMP01"


class TestPostRuns:
    def test_trigger_run_returns_202(self, api_client):
        with patch("ikon.api.routers.runs._run_pipeline_in_thread"):
            resp = api_client.post(
                "/api/v1/runs",
                json={"triggered_by": "test", "from_cache": None},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "running"
        assert data["triggered_by"] == "test"

    def test_trigger_run_creates_db_entry(self, api_client, db_conn):
        from ikon.repository import RunRepository

        with patch("ikon.api.routers.runs._run_pipeline_in_thread"):
            resp = api_client.post("/api/v1/runs", json={"triggered_by": "test"})

        run_id = resp.json()["run_id"]
        run = RunRepository(db_conn).get(run_id)
        assert run is not None
        assert run["status"] == "running"

    def test_trigger_run_conflict_returns_409(self, api_client):
        with patch("ikon.api.routers.runs._run_pipeline_in_thread"):
            resp1 = api_client.post("/api/v1/runs", json={"triggered_by": "test"})
            assert resp1.status_code == 202

            # Második indítás ugyanúgy → futó pipeline létezik → 409
            resp2 = api_client.post("/api/v1/runs", json={"triggered_by": "test"})
        assert resp2.status_code == 409
        assert resp2.json()["detail"]["code"] == "CONFLICT"


class TestRunSummary:
    def test_run_summary_not_found(self, api_client):
        resp = api_client.get("/api/v1/runs/NOPE/summary")
        assert resp.status_code == 404

    def test_run_summary_returns_structure(self, api_client, db_conn):
        from tests.conftest import insert_article

        insert_run(db_conn, run_id="SUM01")
        insert_article(db_conn, run_id="SUM01", article_id="art01", url="https://t.hu/1")

        resp = api_client.get("/api/v1/runs/SUM01/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "category_counts" in data
        assert "source_distribution" in data
        assert "keyword_stats" in data
