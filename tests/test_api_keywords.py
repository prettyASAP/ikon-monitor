"""
/api/v1/keywords és /api/v1/config/scoring endpoint tesztek.
"""
from __future__ import annotations

import pytest

from ikon.keywords import KEYWORDS, TV_RADIO_KEYWORDS, HTEN_KEYWORDS, NAPI_KEYWORDS, IKO_COMBINED_KEYWORDS

_ALL_SEEDED = sum(
    len(kws)
    for d in [IKO_COMBINED_KEYWORDS, KEYWORDS, TV_RADIO_KEYWORDS, HTEN_KEYWORDS, NAPI_KEYWORDS]
    for kws in d.values()
)


class TestListKeywords:
    def test_list_returns_all_seeded(self, api_client):
        resp = api_client.get("/api/v1/keywords")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == _ALL_SEEDED
        assert all("keyword" in kw and "tier" in kw and "is_active" in kw for kw in data)

    def test_filter_by_tier(self, api_client):
        resp = api_client.get("/api/v1/keywords?tier=tier1_specifikus")
        assert resp.status_code == 200
        data = resp.json()
        assert all(kw["tier"] == "tier1_specifikus" for kw in data)
        assert len(data) > 0

    def test_active_only_filter(self, api_client):
        # Alapból mind aktív
        resp = api_client.get("/api/v1/keywords?active_only=true")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == _ALL_SEEDED


class TestCreateKeyword:
    def test_create_returns_201(self, api_client):
        resp = api_client.post(
            "/api/v1/keywords",
            json={"keyword": "ÚjTesztKulcsszó", "tier": "tier2_kozepes"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["keyword"] == "ÚjTesztKulcsszó"
        assert data["tier"] == "tier2_kozepes"
        assert data["is_active"] is True

    def test_create_duplicate_returns_409(self, api_client):
        api_client.post(
            "/api/v1/keywords",
            json={"keyword": "DuplikátumSzó", "tier": "tier3_generikus"},
        )
        resp = api_client.post(
            "/api/v1/keywords",
            json={"keyword": "DuplikátumSzó", "tier": "tier3_generikus"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "CONFLICT"

    def test_create_invalid_tier_returns_422(self, api_client):
        resp = api_client.post(
            "/api/v1/keywords",
            json={"keyword": "ValidSzó", "tier": "invalid_tier"},
        )
        assert resp.status_code == 422

    def test_create_empty_keyword_returns_422(self, api_client):
        resp = api_client.post(
            "/api/v1/keywords",
            json={"keyword": "", "tier": "tier1_specifikus"},
        )
        assert resp.status_code == 422


class TestPatchKeyword:
    def test_deactivate_keyword(self, api_client):
        create_resp = api_client.post(
            "/api/v1/keywords",
            json={"keyword": "DeaktiválandóSzó", "tier": "tier2_kozepes"},
        )
        kw_id = create_resp.json()["id"]

        patch_resp = api_client.patch(
            f"/api/v1/keywords/{kw_id}",
            json={"is_active": False},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["is_active"] is False

        # Aktív szűrőben nem jelenik meg
        active_resp = api_client.get("/api/v1/keywords?active_only=true")
        active_ids = [kw["id"] for kw in active_resp.json()]
        assert kw_id not in active_ids

    def test_change_tier(self, api_client):
        create_resp = api_client.post(
            "/api/v1/keywords",
            json={"keyword": "TierVáltóSzó", "tier": "tier3_generikus"},
        )
        kw_id = create_resp.json()["id"]

        patch_resp = api_client.patch(
            f"/api/v1/keywords/{kw_id}",
            json={"tier": "tier1_specifikus"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["tier"] == "tier1_specifikus"

    def test_patch_not_found_returns_404(self, api_client):
        resp = api_client.patch("/api/v1/keywords/99999", json={"is_active": False})
        assert resp.status_code == 404


class TestDeleteKeyword:
    def test_delete_returns_204(self, api_client):
        create_resp = api_client.post(
            "/api/v1/keywords",
            json={"keyword": "TörlendőSzó", "tier": "tier3_generikus"},
        )
        kw_id = create_resp.json()["id"]

        del_resp = api_client.delete(f"/api/v1/keywords/{kw_id}")
        assert del_resp.status_code == 204

        # Listán nincs többé
        resp = api_client.get("/api/v1/keywords")
        kw_ids = [kw["id"] for kw in resp.json()]
        assert kw_id not in kw_ids

    def test_delete_not_found_returns_404(self, api_client):
        resp = api_client.delete("/api/v1/keywords/99999")
        assert resp.status_code == 404


class TestScoringConfig:
    def test_get_scoring_config_returns_values(self, api_client):
        resp = api_client.get("/api/v1/config/scoring")
        assert resp.status_code == 200
        data = resp.json()
        assert "tier1_base_score" in data
        assert "threshold_relevant" in data
        assert data["tier1_base_score"] == 40
        assert data["threshold_relevant"] == 20
