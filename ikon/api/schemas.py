"""
Pydantic DTO-k (Data Transfer Objects) az API réteghez.

Ezek a modellek az `ikon/models.py` Pydantic modellek API-kompatibilis
változatai. A frontend csapat ezek alapján generálhat TypeScript típusokat.
"""
from __future__ import annotations

from typing import Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Generikus paginator
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    limit: int
    offset: int
    has_more: bool


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------

class ArticleOut(BaseModel):
    article_id: str
    run_id: str
    url: str
    title: str
    source: str
    source_type: str
    published_date: str
    published_date_iso: Optional[str] = None
    published_time: str
    excerpt: str
    matched_keywords: List[str]
    best_tier: str
    score: int
    score_reason: str
    category: str
    feedback_decision: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewer_note: Optional[str] = None
    scored_at: str


# ---------------------------------------------------------------------------
# Pipeline Runs
# ---------------------------------------------------------------------------

class RunOut(BaseModel):
    run_id: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    time_window_hours: int = 168
    keyword_profile: str = "iko_ceg"
    total_raw: int = 0
    total_unique: int = 0
    relevant: int = 0
    review: int = 0
    noise: int = 0
    error_msg: Optional[str] = None
    triggered_by: Optional[str] = None
    duplicate_rate: Optional[float] = None


class RunCreateRequest(BaseModel):
    from_cache: Optional[str] = Field(
        default=None,
        description="Elérési út egy meglévő nyers CSV-hez (scraping kihagyásához)"
    )
    triggered_by: str = Field(
        default="api",
        description="A hívó azonosítója (pl. 'api', 'user@example.com')"
    )
    time_window_hours: int = Field(
        default=168,
        description="Keresési időablak órában (pl. 24 = napi, 168 = heti)"
    )
    keyword_profile: str = Field(
        default="iko_ceg",
        description="Kulcsszó profil: 'iko_ceg' vagy 'tv_radio_musorok'"
    )


class RunSummary(BaseModel):
    run_id: str
    category_counts: Dict[str, int]
    source_distribution: List[Dict]
    keyword_stats: List[Dict]


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class FeedbackIn(BaseModel):
    decision: str = Field(
        ...,
        description="Döntés: 'releváns' vagy 'nem_releváns'",
        pattern=r"^(relev[áa]ns|nem_relev[áa]ns)$",
    )
    reviewer_id: Optional[str] = Field(
        default=None,
        description="Reviewer azonosítója (pl. email cím)"
    )
    reviewer_note: str = Field(default="", description="Opcionális megjegyzés")


class FeedbackOut(BaseModel):
    url: str
    decision: str
    reviewer_id: Optional[str] = None
    reviewer_note: str = ""
    original_score: int
    reviewed_at: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BulkFeedbackItem(BaseModel):
    article_id: str
    decision: str = Field(
        ...,
        pattern=r"^(relev[áa]ns|nem_relev[áa]ns)$",
    )


class BulkFeedbackIn(BaseModel):
    items: List[BulkFeedbackItem]
    reviewer_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

class KeywordOut(BaseModel):
    id: int
    keyword: str
    tier: str
    is_active: bool
    profile: str = "iko_ceg"
    created_at: str
    updated_at: str


class KeywordIn(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=200)
    tier: str = Field(
        ...,
        description="tier1_specifikus | tier2_kozepes | tier3_generikus",
        pattern=r"^tier[123]_(specifikus|kozepes|generikus)$",
    )
    profile: str = Field(default="iko_ceg", description="iko_ceg | tv_radio_musorok")


class KeywordPatch(BaseModel):
    is_active: Optional[bool] = None
    tier: Optional[str] = Field(
        default=None,
        pattern=r"^tier[123]_(specifikus|kozepes|generikus)$",
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class ScoringConfigOut(BaseModel):
    tier1_base_score: int
    tier2_base_score: int
    tier3_base_score: int
    false_positive_penalty: int
    context_bonus_per_word: int
    context_bonus_cap: int
    bulvar_tier3_penalty: int
    threshold_relevant: int
    threshold_review: int


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthOut(BaseModel):
    status: str
    db: str
    schema_version: int
