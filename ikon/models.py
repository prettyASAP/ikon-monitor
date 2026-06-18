"""
Core data models – az egyetlen igazság forrása az adat struktúráját illetően.

A Pydantic v2 modellek validálnak, serializálnak és dokumentálnak egyszerre.
A senior DS csapat ezeket a modelleket importálja; a séma itt van definiálva.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field, model_validator


# ---------------------------------------------------------------------------
# Enumerációk
# ---------------------------------------------------------------------------

class Category(str, Enum):
    RELEVANT = "releváns"
    REVIEW = "felülvizsgálandó"
    NOISE = "zaj"


class SourceType(str, Enum):
    MEDIA = "médiaipari"
    TABLOID = "bulvár"
    OTHER = "egyéb"


class KeywordTier(str, Enum):
    SPECIFIC = "tier1_specifikus"
    MEDIUM = "tier2_kozepes"
    GENERIC = "tier3_generikus"


class FeedbackDecision(str, Enum):
    RELEVANT = "releváns"
    NOT_RELEVANT = "nem_releváns"


# ---------------------------------------------------------------------------
# Nyers cikk (scraper kimenet)
# ---------------------------------------------------------------------------

class RawArticle(BaseModel):
    """Egy hirkereso.hu találat, közvetlenül a scraperből.

    Egy URL több kulcsszóra is megjelenhet – a deduplikáció a pipeline-ban történik.
    """
    url: str = Field(description="Tényleges cikk URL (rd. redirect nélkül)")
    title: str = Field(description="Cikk títele")
    source: str = Field(description="Hírforrás neve (pl. 'Médiapiac', 'Blikk')")
    published_date: str = Field(description="Megjelenés dátuma, 'YYYY.MM.DD' formátum")
    published_time: str = Field(default="", description="Megjelenés időpontja, 'HH:MM' formátum")
    excerpt: str = Field(default="", description="Lead / előzetes szöveg")
    matched_keyword: str = Field(description="A hirkereso.hu keresőszó, amely ezt a cikket visszaadta")
    keyword_tier: str = Field(description="A kulcsszó tier-je (tier1/2/3)")
    scraped_at: datetime = Field(default_factory=datetime.utcnow)

    @computed_field
    @property
    def article_id(self) -> str:
        """Stabil, URL-alapú azonosító – deduplikációhoz és DB primary key-hez."""
        return hashlib.sha256(self.url.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Pontozott, deduplikált cikk
# ---------------------------------------------------------------------------

class ScoredArticle(BaseModel):
    """Egy egyedi cikk a teljes relevancia analízissel.

    Ez a pipeline fő kimeneti egysége. Az SQLite `articles` tábla ezt tükrözi.
    """
    url: str
    title: str
    source: str
    source_type: SourceType
    published_date: str
    published_time: str
    excerpt: str

    matched_keywords: list[str] = Field(description="Összes kulcsszó, amely ezt a cikket visszaadta")
    best_tier: KeywordTier = Field(description="A legjobb (legspecifikusabb) tier az egyező kulcsszavak közül")

    score: int = Field(ge=0, le=100, description="Relevancia pontszám (0–100)")
    score_reason: str = Field(description="Pontszám összetevői, ember által olvasható formában")
    category: Category

    # Opcionális emberi döntés (feedback.json-ból töltődik)
    feedback_decision: Optional[FeedbackDecision] = None
    feedback_reviewed_at: Optional[datetime] = None

    scored_at: datetime = Field(default_factory=datetime.utcnow)

    @computed_field
    @property
    def article_id(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()[:16]

    @computed_field
    @property
    def effective_category(self) -> Category:
        """A feedback felülírja az automatikus kategóriát, ha jelen van."""
        if self.feedback_decision == FeedbackDecision.RELEVANT:
            return Category.RELEVANT
        if self.feedback_decision == FeedbackDecision.NOT_RELEVANT:
            return Category.NOISE
        return self.category


# ---------------------------------------------------------------------------
# Emberi visszajelzés
# ---------------------------------------------------------------------------

class FeedbackEntry(BaseModel):
    """Egy reviewer döntése egy cikkről.

    A `feedback.json`-t ez a modell serializálja/deserializálja.
    """
    url: str
    decision: FeedbackDecision
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    original_score: int = Field(ge=0, le=100)
    reviewer_note: str = Field(default="")


# ---------------------------------------------------------------------------
# Pipeline futás metaadat
# ---------------------------------------------------------------------------

class PipelineRun(BaseModel):
    """Egy teljes pipeline futás összefoglalója."""
    run_id: str = Field(description="ISO timestamp-alapú egyedi azonosító")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    time_window_hours: int = Field(default=168, description="Keresési időablak (alapértelmezés: 1 hét)")

    total_raw_articles: int = Field(default=0)
    total_unique_articles: int = Field(default=0)
    relevant_count: int = Field(default=0)
    review_count: int = Field(default=0)
    noise_count: int = Field(default=0)

    keyword_profile: str = Field(default="iko_ceg")  # iko_ceg | tv_radio_musorok
    status: str = Field(default="running")  # running | completed | failed
    error_message: Optional[str] = None

    @computed_field
    @property
    def duplicate_rate(self) -> float:
        if self.total_raw_articles == 0:
            return 0.0
        return round(1 - self.total_unique_articles / self.total_raw_articles, 3)
