"""
Konfigurációs réteg – YAML-alapú beállítások betöltése és validálása.

Importálás:
    from ikon.config import load_config, Config
    cfg = load_config()
    print(cfg.scoring.tier1_base_score)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"


# ---------------------------------------------------------------------------
# Konfigurációs adatstruktúrák (dataclass, Pydantic nélkül – egyszerűség kedvéért)
# ---------------------------------------------------------------------------

@dataclass
class ScoringThresholds:
    relevant: int = 20
    review: int = 8


@dataclass
class ScoringConfig:
    tier1_base_score: int = 40
    tier2_base_score: int = 20
    tier3_base_score: int = 5
    false_positive_penalty: int = 2
    tier2_false_positive_penalty: int = 8
    context_bonus_per_word: int = 2
    context_bonus_cap: int = 15
    bulvar_tier3_penalty: int = 3
    thresholds: ScoringThresholds = field(default_factory=ScoringThresholds)


@dataclass
class ScrapingConfig:
    time_window_hours: int = 168
    request_delay_seconds: float = 1.2
    request_timeout_seconds: int = 15
    base_url: str = "https://www.hirkereso.hu/search"
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


@dataclass
class StorageConfig:
    db_path: str = "data/ikon.db"
    feedback_path: str = "output/feedback.json"


@dataclass
class ExportConfig:
    output_dir: str = "output"
    export_parquet: bool = True
    excel_row_height: int = 60


@dataclass
class Config:
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    export: ExportConfig = field(default_factory=ExportConfig)


# ---------------------------------------------------------------------------
# Betöltés
# ---------------------------------------------------------------------------

def load_config(path: Optional[Path] = None) -> Config:
    """Betölti a settings.yaml-t és visszaad egy Config objektumot.

    Ha a fájl nem létezik, visszatér az alapértelmezett beállításokkal.
    """
    config_path = path or _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return Config()

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    s = raw.get("scoring", {})
    thresholds_raw = s.get("thresholds", {})
    scoring = ScoringConfig(
        tier1_base_score=s.get("tier1_base_score", 40),
        tier2_base_score=s.get("tier2_base_score", 20),
        tier3_base_score=s.get("tier3_base_score", 5),
        false_positive_penalty=s.get("false_positive_penalty", 2),
        tier2_false_positive_penalty=s.get("tier2_false_positive_penalty", 8),
        context_bonus_per_word=s.get("context_bonus_per_word", 2),
        context_bonus_cap=s.get("context_bonus_cap", 15),
        bulvar_tier3_penalty=s.get("bulvar_tier3_penalty", 3),
        thresholds=ScoringThresholds(
            relevant=thresholds_raw.get("relevant", 20),
            review=thresholds_raw.get("review", 8),
        ),
    )

    sc = raw.get("scraping", {})
    scraping = ScrapingConfig(
        time_window_hours=sc.get("time_window_hours", 168),
        request_delay_seconds=sc.get("request_delay_seconds", 1.2),
        request_timeout_seconds=sc.get("request_timeout_seconds", 15),
        base_url=sc.get("base_url", "https://www.hirkereso.hu/search"),
        user_agent=sc.get("user_agent", ScrapingConfig.user_agent),
    )

    st = raw.get("storage", {})
    storage = StorageConfig(
        db_path=os.environ.get("IKON_DB_PATH") or st.get("db_path", "data/ikon.db"),
        feedback_path=st.get("feedback_path", "output/feedback.json"),
    )

    ex = raw.get("export", {})
    export = ExportConfig(
        output_dir=ex.get("output_dir", "output"),
        export_parquet=ex.get("export_parquet", True),
        excel_row_height=ex.get("excel_row_height", 60),
    )

    return Config(scoring=scoring, scraping=scraping, storage=storage, export=export)
