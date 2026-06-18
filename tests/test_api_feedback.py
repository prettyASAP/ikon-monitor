"""
/api/v1/feedback endpoint tesztek.
"""
from __future__ import annotations

import pytest

from tests.conftest import insert_article, insert_run


@pytest.fixture
def article_in_db(db_conn):
    """Egy cikk a tesztelési adatbázisban."""
    insert_run(db_conn, run_id="FBRUN")
    insert_article(
        db_conn,
        run_id="FBRUN",
        article_id="fb_article",
        url="https://test.hu/feedback-cikk",
        score=30,
    )
    return "fb_article"


class TestFeedbackLifecycle:
    def test_post_feedback_returns_200(self, api_client, article_in_db):
        resp = api_client.post(
            f"/api/v1/feedback/{article_in_db}",
            json={"decision": "releváns", "reviewer_id": "user1", "reviewer_note": "OK"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "releváns"
        assert data["reviewer_id"] == "user1"
        assert data["reviewer_note"] == "OK"
        assert data["original_score"] == 30

    def test_get_feedback_list(self, api_client, article_in_db):
        api_client.post(
            f"/api/v1/feedback/{article_in_db}",
            json={"decision": "nem_releváns"},
        )

        resp = api_client.get("/api/v1/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["decision"] == "nem_releváns"

    def test_upsert_feedback_updates_decision(self, api_client, article_in_db):
        api_client.post(f"/api/v1/feedback/{article_in_db}", json={"decision": "nem_releváns"})
        resp = api_client.post(f"/api/v1/feedback/{article_in_db}", json={"decision": "releváns"})
        assert resp.status_code == 200
        assert resp.json()["decision"] == "releváns"

        # List-en is frissül
        list_resp = api_client.get("/api/v1/feedback")
        assert list_resp.json()["total"] == 1  # nem duplikálódott

    def test_delete_feedback_returns_204(self, api_client, article_in_db):
        api_client.post(f"/api/v1/feedback/{article_in_db}", json={"decision": "releváns"})

        del_resp = api_client.delete(f"/api/v1/feedback/{article_in_db}")
        assert del_resp.status_code == 204

        # Törlés után a lista üres
        list_resp = api_client.get("/api/v1/feedback")
        assert list_resp.json()["total"] == 0

    def test_delete_feedback_not_found(self, api_client, article_in_db):
        # Feedback nélküli cikk törlési kísérlete
        resp = api_client.delete(f"/api/v1/feedback/{article_in_db}")
        assert resp.status_code == 404

    def test_feedback_on_unknown_article_returns_404(self, api_client):
        resp = api_client.post(
            "/api/v1/feedback/nonexistent_article",
            json={"decision": "releváns"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "NOT_FOUND"

    def test_invalid_decision_returns_422(self, api_client, article_in_db):
        resp = api_client.post(
            f"/api/v1/feedback/{article_in_db}",
            json={"decision": "invalid_value"},
        )
        assert resp.status_code == 422


class TestBulkFeedback:
    @pytest.fixture
    def three_articles(self, db_conn):
        insert_run(db_conn, run_id="BULKRUN")
        for i in range(3):
            insert_article(
                db_conn,
                run_id="BULKRUN",
                article_id=f"bulk_{i}",
                url=f"https://test.hu/bulk-{i}",
                score=20 + i,
            )
        return [f"bulk_{i}" for i in range(3)]

    def test_bulk_submit_returns_success_count(self, api_client, three_articles):
        resp = api_client.post(
            "/api/v1/feedback/bulk",
            json={
                "items": [{"article_id": a, "decision": "releváns"} for a in three_articles],
                "reviewer_id": "bulk_user",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] == 3
        assert data["errors"] == []

    def test_bulk_submit_handles_unknown_article(self, api_client, three_articles):
        resp = api_client.post(
            "/api/v1/feedback/bulk",
            json={
                "items": [
                    {"article_id": three_articles[0], "decision": "releváns"},
                    {"article_id": "nonexistent_xyz", "decision": "releváns"},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["article_id"] == "nonexistent_xyz"

    def test_bulk_submit_visible_in_feedback_list(self, api_client, three_articles):
        api_client.post(
            "/api/v1/feedback/bulk",
            json={"items": [{"article_id": a, "decision": "nem_releváns"} for a in three_articles]},
        )
        resp = api_client.get("/api/v1/feedback")
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_bulk_invalid_decision_returns_422(self, api_client, three_articles):
        resp = api_client.post(
            "/api/v1/feedback/bulk",
            json={"items": [{"article_id": three_articles[0], "decision": "rossz_érték"}]},
        )
        assert resp.status_code == 422
