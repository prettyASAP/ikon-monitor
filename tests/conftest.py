"""
pytest fixture-ök a teszteléshez.

A DS csapat ezeket importálva írhat gyors unit teszteket anélkül,
hogy a teljes pipeline-t el kellene indítani.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ikon.config import (
    Config,
    ExportConfig,
    ScoringConfig,
    ScoringThresholds,
    ScrapingConfig,
    StorageConfig,
)
from ikon.database import Database
from ikon.models import (
    Category,
    FeedbackDecision,
    FeedbackEntry,
    KeywordTier,
    RawArticle,
    ScoredArticle,
    SourceType,
)
from ikon.repository import KeywordRepository


# ---------------------------------------------------------------------------
# Alap konfiguráció
# ---------------------------------------------------------------------------

@pytest.fixture
def default_config() -> Config:
    return Config(
        scoring=ScoringConfig(
            tier1_base_score=40,
            tier2_base_score=20,
            tier3_base_score=5,
            false_positive_penalty=2,
            context_bonus_per_word=2,
            context_bonus_cap=15,
            bulvar_tier3_penalty=3,
            thresholds=ScoringThresholds(relevant=20, review=8),
        ),
        scraping=ScrapingConfig(),
        storage=StorageConfig(db_path=":memory:"),
        export=ExportConfig(),
    )


@pytest.fixture
def scoring_cfg(default_config: Config) -> ScoringConfig:
    return default_config.scoring


# ---------------------------------------------------------------------------
# Adatbázis fixture-ök
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path) -> str:
    """Ideiglenes SQLite fájl elérési útja."""
    return str(tmp_path / "test.db")


@pytest.fixture
def db_conn(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Nyitott SQLite kapcsolat a tesztelési adatbázishoz (v002 sémával)."""
    with Database(db_path) as db:
        db.run_migrations()
        yield db.conn


# ---------------------------------------------------------------------------
# API test client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client(db_path: str, default_config: Config) -> Generator[TestClient, None, None]:
    """TestClient, amely a tesztelési adatbázist használja.

    - A lifespan futtatja a migrációt és a kulcsszó-seedelést.
    - A get_config és get_db dependency-k le vannak cserélve.
    """
    test_cfg = Config(
        scoring=default_config.scoring,
        scraping=default_config.scraping,
        storage=StorageConfig(db_path=db_path),
        export=default_config.export,
    )

    from ikon.api.app import app
    from ikon.api.dependencies import get_config, get_db

    def override_get_config() -> Config:
        return test_cfg

    def override_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=3000")
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_config] = override_get_config
    app.dependency_overrides[get_db] = override_get_db

    with patch("ikon.api.app.load_config", return_value=test_cfg):
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Scoring unit test fixture-ök (változatlan)
# ---------------------------------------------------------------------------

@pytest.fixture
def tier1_raw_article() -> RawArticle:
    return RawArticle(
        url="https://media1.hu/2026/06/iko-musorgyarto-nyert-dijat",
        title="IKO Műsorgyártó elnyerte az Év Produkciós Cége díjat",
        source="Media1",
        published_date="2026.06.16",
        published_time="09:30",
        excerpt="Az IKO Műsorgyártó Magyarország Kft. ismét bizonyított a televíziós piacon.",
        matched_keyword="IKO Műsorgyártó",
        keyword_tier="tier1_specifikus",
    )


@pytest.fixture
def tier2_false_positive_article() -> RawArticle:
    return RawArticle(
        url="https://hvg.hu/2026/06/ikonikus-tarsadalmi-valtozas",
        title="Ikonikus társadalmi változás zajlik Magyarországon",
        source="hvg.hu",
        published_date="2026.06.15",
        published_time="14:00",
        excerpt="Az ikonikus személyiségek szerepe megváltozott a médiában.",
        matched_keyword="IKO",
        keyword_tier="tier2_kozepes",
    )


@pytest.fixture
def tier3_media_article() -> RawArticle:
    return RawArticle(
        url="https://mediapiac.com/2026/06/nezettség-adatok-tv2",
        title="Rekordnézettség a TV2 tavaszi szezonban – Nielsen adatok",
        source="Médiapiac",
        published_date="2026.06.14",
        published_time="11:00",
        excerpt="A televíziós közönségarány adatai szerint a kereskedelmi csatornák nézettségi adatai növekedtek.",
        matched_keyword="nézettség",
        keyword_tier="tier3_generikus",
    )


@pytest.fixture
def scored_relevant_article() -> ScoredArticle:
    return ScoredArticle(
        url="https://media1.hu/2026/06/iko-musorgyarto-nyert-dijat",
        title="IKO Műsorgyártó elnyerte az Év Produkciós Cége díjat",
        source="Media1",
        source_type=SourceType.MEDIA,
        published_date="2026.06.16",
        published_time="09:30",
        excerpt="Az IKO Műsorgyártó Magyarország Kft. ismét bizonyított.",
        matched_keywords=["IKO Műsorgyártó", "IKO"],
        best_tier=KeywordTier.SPECIFIC,
        score=42,
        score_reason="IKO Műsorgyártó(T1)+40 | IKO(FP,T2)+2",
        category=Category.RELEVANT,
    )


@pytest.fixture
def feedback_entry(scored_relevant_article: ScoredArticle) -> FeedbackEntry:
    return FeedbackEntry(
        url=scored_relevant_article.url,
        decision=FeedbackDecision.RELEVANT,
        original_score=scored_relevant_article.score,
        reviewer_note="Pontos találat",
    )


# ---------------------------------------------------------------------------
# DB adat-segédfüggvények
# ---------------------------------------------------------------------------

def insert_run(conn: sqlite3.Connection, run_id: str = "RUN001", status: str = "completed") -> None:
    conn.execute(
        """INSERT INTO pipeline_runs
           (run_id, started_at, status, time_window_hours, total_raw, total_unique,
            relevant, review, noise)
           VALUES (?, datetime('now'), ?, 168, 10, 8, 3, 3, 2)""",
        (run_id, status),
    )
    conn.commit()


def insert_article(
    conn: sqlite3.Connection,
    *,
    run_id: str = "RUN001",
    article_id: str = "article01",
    url: str = "https://test.hu/cikk1",
    title: str = "Teszt cikk",
    excerpt: str = "Teszt tartalom szövege",
    source: str = "Media1",
    source_type: str = "médiaipari",
    best_tier: str = "tier1_specifikus",
    score: int = 25,
    category: str = "releváns",
    matched_keywords: list | None = None,
    published_date_iso: str = "2026-06-16",
) -> None:
    kws = json.dumps(matched_keywords or ["IKO Műsorgyártó"])
    conn.execute(
        """INSERT INTO articles
           (article_id, run_id, url, title, source, source_type,
            published_date, published_date_iso, published_time,
            excerpt, matched_keywords, best_tier, score, score_reason,
            category, scored_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
        (
            article_id, run_id, url, title, source, source_type,
            "2026.06.16", published_date_iso, "10:00",
            excerpt, kws, best_tier, score, "teszt ok", category,
        ),
    )
    conn.commit()
