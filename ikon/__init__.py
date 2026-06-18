"""
ikon – IKO Média Monitoring pipeline csomag.

Publikus interfész (senior DS csapatnak):

    from ikon import load_config, run_pipeline, export_excel
    from ikon.models import RawArticle, ScoredArticle, Category
    from ikon.scoring import score_article, is_false_positive, classify_source
    from ikon.database import Database
"""
from ikon.config import Config, load_config
from ikon.models import (
    Category,
    FeedbackDecision,
    FeedbackEntry,
    KeywordTier,
    PipelineRun,
    RawArticle,
    ScoredArticle,
    SourceType,
)

__version__ = "0.2.0"
__all__ = [
    # Config
    "Config",
    "load_config",
    # Models
    "RawArticle",
    "ScoredArticle",
    "FeedbackEntry",
    "PipelineRun",
    "Category",
    "KeywordTier",
    "SourceType",
    "FeedbackDecision",
    # Pipeline (lazy import to avoid circular deps at module load)
    # Use: from ikon.pipeline import run_pipeline
    # Use: from ikon.exporter import export_excel
]
