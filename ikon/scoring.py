"""
Relevancia scoring motor – tesztelhetőre és hangolhatóra tervezve.

Minden publikus függvény tiszta: nem tartalmaz I/O-t, csak transzformációt.
A DS csapat egységtesztelheti és kísérletezhet a paraméterekkel anélkül,
hogy a pipeline többi részét futtatná.

Importálás:
    from ikon.scoring import score_article, classify_source, is_false_positive
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple

from ikon.config import ScoringConfig
from ikon.keywords import (
    FALSE_POSITIVE_PATTERNS,
    FULL_NAME_REQUIRED,
    KEYWORD_TIER,
    CONTEXT_WORDS,
    SOURCES_MEDIA,
    SOURCES_TABLOID,
    TIER3_MEDIA_CORE,
    TV_REQUIRED_CONTEXT,
    T3_NO_BULVAR_KEYWORDS,
)
from ikon.models import Category, SourceType


# ---------------------------------------------------------------------------
# False positive detekció
# ---------------------------------------------------------------------------

def is_false_positive(keyword: str, title: str, excerpt: str) -> bool:
    """Meghatározza, hogy egy kulcsszó-egyezés valódi találat-e.

    Args:
        keyword: A hirkereso-n keresett kulcsszó.
        title:   A cikk eredeti (case-preserved) títele.
        excerpt: A cikk leadje (case-preserved).

    Returns:
        True, ha az egyezés valószínűleg zaj (false positive).
    """
    text_original = f"{title} {excerpt}"
    text_lower = text_original.lower()

    # IKO-kulcsszavak: nagybetűs \bIKO\b jelenléte dönti el.
    if keyword.upper().startswith("IKO"):
        return not bool(re.search(r"\bIKO\b", text_original))

    # TV T3/T2 magas-FP kulcsszavak: show-kontextus hiánya → FP (whitelist logika).
    if keyword in TV_REQUIRED_CONTEXT:
        required = TV_REQUIRED_CONTEXT[keyword]
        if not re.search(required, text_lower, re.IGNORECASE):
            return True
        # Személy-nevek: kontextus megvan, de a teljes névnek is meg kell jelennie
        if keyword in FULL_NAME_REQUIRED:
            return not bool(re.search(re.escape(keyword), text_lower, re.IGNORECASE))
        return False

    # Személy-nevek TV_REQUIRED_CONTEXT nélkül: teljes névalak kötelező
    if keyword in FULL_NAME_REQUIRED:
        if not re.search(re.escape(keyword), text_lower, re.IGNORECASE):
            return True  # Frázis hiánya → FP
        # Frázis megvan → FALSE_POSITIVE_PATTERNS is ellenőrzendő

    # Általános FP pattern-ek (blacklist logika).
    patterns = FALSE_POSITIVE_PATTERNS.get(keyword, [])
    for pattern in patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True

    return False


# ---------------------------------------------------------------------------
# Forrástípus klasszifikáció
# ---------------------------------------------------------------------------

def classify_source(source: str) -> SourceType:
    """Visszaadja a forrás típusát a SOURCES_MEDIA és SOURCES_TABLOID listák alapján."""
    stripped = source.strip()
    if stripped in SOURCES_MEDIA:
        return SourceType.MEDIA
    if stripped in SOURCES_TABLOID:
        return SourceType.TABLOID
    return SourceType.OTHER


# ---------------------------------------------------------------------------
# Pontszámítás
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoreResult:
    """A score_article() visszatérési értéke."""
    score: int
    reason: str


def score_article(
    matched_keywords: list[str],
    title: str,
    excerpt: str,
    source: str,
    cfg: ScoringConfig,
) -> ScoreResult:
    """Kiszámolja egy cikk relevancia pontszámát.

    A pontszám összetevői:
    - Tier1 egyezés: +cfg.tier1_base_score (FP esetén: +cfg.false_positive_penalty)
    - Tier2 egyezés: +cfg.tier2_base_score (FP esetén: +cfg.false_positive_penalty)
    - Tier3 egyezés: +cfg.tier3_base_score (bulvár forrástípusnál: -cfg.bulvar_tier3_penalty)
    - Kontextus bónusz: +cfg.context_bonus_per_word / szó, max cfg.context_bonus_cap

    Returns:
        ScoreResult(score=0..100, reason="ember által olvasható magyarázat")
    """
    source_type = classify_source(source)
    score = 0
    parts: list[str] = []

    for kw in matched_keywords:
        tier = KEYWORD_TIER.get(kw, "tier3_generikus")
        fp = is_false_positive(kw, title, excerpt)

        if tier == "tier1_specifikus":
            pts = cfg.false_positive_penalty if fp else cfg.tier1_base_score
            label = f"FP,T1" if fp else "T1"
            score += pts
            parts.append(f"{kw}({label})+{pts}")

        elif tier == "tier2_kozepes":
            pts = cfg.tier2_false_positive_penalty if fp else cfg.tier2_base_score
            label = "FP,T2" if fp else "T2"
            score += pts
            parts.append(f"{kw}({label})+{pts}")

        elif tier == "tier3_generikus":
            # FP detekció T3-ra is érvényes: kontextus-bónusz context+T3 összegét akár
            # 20+ pontig is tolhatja, ezért a hamis találatok kizárása itt is szükséges.
            if fp:
                parts.append(f"{kw}(FP,T3)+0")
                continue
            pts = cfg.tier3_base_score
            # TV show T3 kulcsszavaknál a bulvárlapok az elsődleges forrás → penalty kizárva
            if source_type == SourceType.TABLOID and kw not in T3_NO_BULVAR_KEYWORDS:
                pts = max(0, pts - cfg.bulvar_tier3_penalty)
                parts.append(f"{kw}(T3,bulvár)+{pts}")
            else:
                parts.append(f"{kw}(T3)+{pts}")
            score += pts

    # Kontextus bónusz
    text_lower = f"{title} {excerpt}".lower()
    ctx_hits = [w for w in CONTEXT_WORDS if w in text_lower]
    ctx_bonus = min(len(ctx_hits) * cfg.context_bonus_per_word, cfg.context_bonus_cap)
    if ctx_hits:
        score += ctx_bonus
        parts.append(f"ctx({','.join(ctx_hits[:4])})+{ctx_bonus}")

    if source_type != SourceType.OTHER:
        parts.append(f"src={source_type.value}")

    return ScoreResult(
        score=min(score, 100),
        reason=" | ".join(parts),
    )


# ---------------------------------------------------------------------------
# Kategorizálás (biztonsági hálókkal)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CategoryFlags:
    """Biztonsági háló feltételek a kategorizáláshoz."""
    has_tier1_keyword: bool = False
    has_tier3_media_core: bool = False


def categorize(
    score: int,
    source_type: SourceType,
    matched_keywords: list[str],
    title: str,
    excerpt: str,
    cfg: ScoringConfig,
) -> tuple[Category, CategoryFlags]:
    """Meghatározza a kategóriát a pontszám és biztonsági hálók alapján.

    Biztonsági hálók (a „minden releváns cikk látszódjon" elvhez):
    1. Ha valódi (nem FP) Tier 1 kulcsszó talált → minimum Felülvizsgálandó.
    2. Ha Tier 3 médiaipari-core kulcsszó + Médiaipari forrás → Felülvizsgálandó.

    Returns:
        (Category, CategoryFlags)
    """
    flags = CategoryFlags(
        has_tier1_keyword=any(
            KEYWORD_TIER.get(kw) == "tier1_specifikus"
            and not is_false_positive(kw, title, excerpt)
            for kw in matched_keywords
        ),
        has_tier3_media_core=(
            source_type == SourceType.MEDIA
            and any(
                KEYWORD_TIER.get(kw) == "tier3_generikus" and kw in TIER3_MEDIA_CORE
                for kw in matched_keywords
            )
        ),
    )

    if score >= cfg.thresholds.relevant:
        return Category.RELEVANT, flags

    # Biztonsági hálók
    if flags.has_tier1_keyword or flags.has_tier3_media_core:
        return Category.REVIEW, flags

    if score >= cfg.thresholds.review:
        return Category.REVIEW, flags

    return Category.NOISE, flags
