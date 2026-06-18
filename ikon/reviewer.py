"""
Emberi felülvizsgálati workflow.

Felelős a reviewer döntések beolvasásáért (Excel) és a ScoredArticle-ökre
való alkalmazásáért. A perzisztencia a Database-ben van – ez a modul
nem ír fájlba közvetlenül.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from ikon.models import FeedbackDecision, FeedbackEntry, ScoredArticle

logger = logging.getLogger(__name__)

_DÖNTÉS_RELEVÁNS = "✅ Releváns"
_DÖNTÉS_NEM = "❌ Nem releváns"


def read_decisions_from_excel(excel_path: Path | str) -> list[FeedbackEntry]:
    """Beolvassa a Felülvizsgálandó lap Döntés oszlopát.

    Returns:
        Kitöltött döntések listája (üres cellákat kihagyja).
    """
    try:
        df = pd.read_excel(excel_path, sheet_name="Felülvizsgálandó")
    except Exception as exc:
        logger.error("Nem sikerült megnyitni az Excel fájlt: %s", exc)
        return []

    missing = [c for c in ("Döntés", "url") if c not in df.columns]
    if missing:
        logger.error("Hiányzó oszlopok a Felülvizsgálandó lapon: %s", missing)
        return []

    entries: list[FeedbackEntry] = []
    today = date.today().isoformat()

    for _, row in df.iterrows():
        raw_döntés = str(row.get("Döntés", "")).strip()
        url = str(row.get("url", "")).strip()

        if not url or raw_döntés in ("", "nan"):
            continue

        if _DÖNTÉS_RELEVÁNS in raw_döntés:
            decision = FeedbackDecision.RELEVANT
        elif _DÖNTÉS_NEM in raw_döntés:
            decision = FeedbackDecision.NOT_RELEVANT
        else:
            logger.debug("Ismeretlen döntés érték, kihagyva: '%s'", raw_döntés)
            continue

        score_raw = row.get("score")
        original_score = int(score_raw) if pd.notna(score_raw) else 0
        note_raw = row.get("Megjegyzés")
        reviewer_note = str(note_raw).strip() if pd.notna(note_raw) else ""

        entries.append(FeedbackEntry(
            url=url,
            decision=decision,
            original_score=original_score,
            reviewer_note=reviewer_note,
        ))

    logger.info(
        "Döntések beolvasva: %d releváns + %d nem releváns",
        sum(1 for e in entries if e.decision == FeedbackDecision.RELEVANT),
        sum(1 for e in entries if e.decision == FeedbackDecision.NOT_RELEVANT),
    )
    return entries


def apply_feedback(
    articles: list[ScoredArticle],
    feedback: dict[str, FeedbackEntry],
) -> list[ScoredArticle]:
    """Visszaad egy új listát, ahol a feedback beillesztve van a modellekbe.

    A ScoredArticle immutable – új objektumokat hoz létre a változtatott mezőkkel.
    Az `effective_category` computed field automatikusan veszi figyelembe a döntést.
    """
    if not feedback:
        return articles

    result: list[ScoredArticle] = []
    for art in articles:
        entry = feedback.get(art.url)
        if entry:
            result.append(art.model_copy(update={
                "feedback_decision": entry.decision,
                "feedback_reviewed_at": entry.reviewed_at,
            }))
        else:
            result.append(art)

    applied = sum(1 for a in result if a.feedback_decision is not None)
    logger.info("Feedback alkalmazva: %d / %d cikkre", applied, len(articles))
    return result
