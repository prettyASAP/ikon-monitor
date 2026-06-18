"""
ETL orchestrátor – scrape → deduplicate → score → persist → export.

Egyetlen `run_pipeline()` hívás lefuttatja a teljes pipeline-t.
Minden lépés naplózva van, a Database auditálja a futás metaadatait.

Importálás:
    from ikon.pipeline import run_pipeline
    run, articles, raw = run_pipeline(cfg)
"""
from __future__ import annotations

import csv
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from ikon.config import Config
from ikon.database import Database
from ikon.models import Category, KeywordTier, PipelineRun, RawArticle, ScoredArticle
from ikon.reviewer import apply_feedback
from ikon.scoring import categorize, classify_source, score_article

logger = logging.getLogger(__name__)

_TIER_ORDER = [KeywordTier.SPECIFIC, KeywordTier.MEDIUM, KeywordTier.GENERIC]
_EMBED_RESCUE_THRESHOLD = 0.60  # e feletti koszinusz-hasonlóság esetén zaj → felülvizsgálandó
_TIER_MAP = {t.value: t for t in KeywordTier}

# Régi CSV formátum oszlopnév → új formátum (backward compatibility)
_OLD_COLUMN_MAP = {
    "datum": "published_date",
    "ido": "published_time",
    "cim": "title",
    "forras": "source",
    "lead": "excerpt",
    "keyword": "matched_keyword",
    "tier": "keyword_tier",
}


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def load_from_csv(path: Path | str) -> list[RawArticle]:
    """Betölti a raw cikkeket egy CSV fájlból (régi és új formátum egyaránt)."""
    path = Path(path)
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    if not raw_rows:
        return []

    # Régi formátum detekció
    first = raw_rows[0]
    if "cim" in first or "datum" in first:
        logger.info("Régi CSV formátum detektálva, oszlopok konvertálva")
        raw_rows = [_remap_old_row(r) for r in raw_rows]

    articles: list[RawArticle] = []
    for row in raw_rows:
        try:
            articles.append(RawArticle(**{k: v for k, v in row.items() if k in RawArticle.model_fields}))
        except Exception as exc:
            logger.debug("Sor kihagyva (hiba): %s – %s", row.get("url", "?"), exc)
    logger.info("CSV betöltve: %d sor (%s)", len(articles), path.name)
    return articles


def _remap_old_row(row: dict) -> dict:
    new = {}
    for k, v in row.items():
        new[_OLD_COLUMN_MAP.get(k, k)] = v
    return new


def save_raw_to_csv(articles: list[RawArticle], path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not articles:
        return
    fieldnames = list(RawArticle.model_fields.keys()) + ["article_id"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for a in articles:
            row = a.model_dump()
            row["article_id"] = a.article_id
            row["scraped_at"] = a.scraped_at.isoformat()
            writer.writerow(row)
    logger.info("Nyers CSV mentve: %s (%d sor)", path, len(articles))


# ---------------------------------------------------------------------------
# Deduplikálás + pontozás
# ---------------------------------------------------------------------------

def _deduplicate_and_score(
    raw_articles: list[RawArticle],
    cfg: Config,
) -> list[ScoredArticle]:
    """Csoportosítja az azonos URL-ű cikkeket, majd pontozza őket.

    Egy URL több kulcsszóra is visszajöhet – a scoring az összes egyező
    kulcsszót figyelembe veszi.
    """
    if not raw_articles:
        return []

    # Csoportosítás URL szerint
    groups: dict[str, list[RawArticle]] = defaultdict(list)
    for a in raw_articles:
        groups[a.url].append(a)

    logger.info("Deduplikálás: %d nyers cikk → %d egyedi URL", len(raw_articles), len(groups))

    scored: list[ScoredArticle] = []
    for url, group in groups.items():
        rep = group[0]
        matched_keywords = list(dict.fromkeys(a.matched_keyword for a in group))

        # Legjobb tier meghatározása
        group_tiers = {_TIER_MAP.get(a.keyword_tier, KeywordTier.GENERIC) for a in group}
        best_tier = next((t for t in _TIER_ORDER if t in group_tiers), KeywordTier.GENERIC)

        source_type = classify_source(rep.source)
        score_result = score_article(
            matched_keywords, rep.title, rep.excerpt, rep.source, cfg.scoring
        )
        category, _ = categorize(
            score_result.score, source_type, matched_keywords,
            rep.title, rep.excerpt, cfg.scoring
        )

        scored.append(ScoredArticle(
            url=url,
            title=rep.title,
            source=rep.source,
            source_type=source_type,
            published_date=rep.published_date,
            published_time=rep.published_time,
            excerpt=rep.excerpt,
            matched_keywords=matched_keywords,
            best_tier=best_tier,
            score=score_result.score,
            score_reason=score_result.reason,
            category=category,
        ))

    # Rendezés dátum + pontszám szerint
    scored.sort(key=lambda a: (a.published_date, a.score), reverse=True)
    logger.info(
        "Pontozás kész: %d releváns | %d felülvizsgálandó | %d zaj",
        sum(1 for a in scored if a.category.value == "releváns"),
        sum(1 for a in scored if a.category.value == "felülvizsgálandó"),
        sum(1 for a in scored if a.category.value == "zaj"),
    )
    return scored


# ---------------------------------------------------------------------------
# Embedding-alapú false-negative rescue
# ---------------------------------------------------------------------------

def _apply_embedding_rescue(articles: list[ScoredArticle]) -> list[ScoredArticle]:
    """Embedding hasonlóság alapján menti a téves negatívokat (zaj → felülvizsgálandó).

    Csak a 'zaj' cikkeken fut le — a releváns és felülvizsgálandó nem változnak.
    Hibánál csendben kihagyja (nem töri el a pipeline-t).
    """
    noise = [a for a in articles if a.category == Category.NOISE]
    if not noise:
        return articles

    try:
        from ikon.embedder import compute_similarity
        texts = [f"{a.title}. {a.excerpt}" for a in noise]
        sims = compute_similarity(texts)

        noise_sims = {id(a): float(sim) for a, sim in zip(noise, sims)}
        result = []
        rescued = 0
        for article in articles:
            if article.category == Category.NOISE:
                sim = noise_sims.get(id(article), 0.0)
                if sim >= _EMBED_RESCUE_THRESHOLD:
                    article = article.model_copy(update={
                        "category": Category.REVIEW,
                        "score_reason": article.score_reason + f" [emb:{sim:.2f}]",
                    })
                    rescued += 1
            result.append(article)

        logger.info(
            "Embedding rescue: %d / %d zaj cikk → felülvizsgálandó (küszöb=%.2f)",
            rescued, len(noise), _EMBED_RESCUE_THRESHOLD,
        )
        return result
    except Exception:
        logger.warning("Embedding rescue kihagyva (sentence-transformers nincs telepítve?)", exc_info=True)

    return articles


# ---------------------------------------------------------------------------
# Fő pipeline függvény
# ---------------------------------------------------------------------------

def run_pipeline(
    cfg: Config,
    from_cache: Optional[Path | str] = None,
    keywords: Optional[list] = None,
    run_id: Optional[str] = None,
) -> tuple[PipelineRun, list[ScoredArticle], list[RawArticle]]:
    """Lefuttatja a teljes ETL pipeline-t.

    Args:
        cfg:        A teljes Config objektum (load_config()-ból).
        from_cache: Ha megadott, a scraping helyett ezt a CSV-t tölt be.
        keywords:   Kulcsszó lista a scrapernek. Ha None, az ALL_KEYWORDS-t használja.
                    Az API a DB-ből tölti és ide adja át (DB-driven keyword management).
        run_id:     Ha az API már létrehozta a sort 'running' státusszal, átadja ide.
                    CLI-ből None → a pipeline generál új run_id-t és létrehozza a sort.

    Returns:
        (PipelineRun, list[ScoredArticle], list[RawArticle])
        A PipelineRun status mezője 'completed' vagy 'failed'.
    """
    pre_created = run_id is not None
    if run_id is None:
        run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run = PipelineRun(
        run_id=run_id,
        time_window_hours=cfg.scraping.time_window_hours,
    )

    with Database(cfg.storage.db_path) as db:
        if not pre_created:
            db.create_run(run)
            # CLI-s futásnál is mentjük a scoring konfigurációt a reprodukálhatósághoz
            import dataclasses as _dc, json as _json
            try:
                snap = _json.dumps(_dc.asdict(cfg.scoring), ensure_ascii=False, default=str)
                db.conn.execute(
                    "UPDATE pipeline_runs SET config_snapshot=? WHERE run_id=?",
                    (snap, run_id),
                )
                db.conn.commit()
            except Exception:
                logger.debug("config_snapshot mentése sikertelen", exc_info=True)

        try:
            # 1. Scraping vagy cache betöltés
            if from_cache:
                raw_articles = load_from_csv(from_cache)
            else:
                from ikon.scraper import scrape_all
                raw_articles = scrape_all(cfg.scraping, keywords=keywords)

                # Nyers CSV mentése
                from datetime import date
                raw_path = Path(cfg.export.output_dir) / f"raw_{date.today().isoformat()}.csv"
                save_raw_to_csv(raw_articles, raw_path)

            run.total_raw_articles = len(raw_articles)
            db.insert_raw_articles(raw_articles, run_id)

            # 2. Deduplikálás + pontozás
            scored_articles = _deduplicate_and_score(raw_articles, cfg)
            run.total_unique_articles = len(scored_articles)

            # 2.5 Embedding-alapú false-negative rescue
            scored_articles = _apply_embedding_rescue(scored_articles)

            # 3. Feedback alkalmazása az adatbázisból
            feedback = db.load_feedback()
            if feedback:
                logger.info("Feedback betöltve az adatbázisból: %d bejegyzés", len(feedback))
                scored_articles = apply_feedback(scored_articles, feedback)

            # 4. Pontozott cikkek mentése DB-be
            db.insert_articles(scored_articles, run_id)

            # 5. Statisztikák
            run.relevant_count = sum(1 for a in scored_articles if a.effective_category.value == "releváns")
            run.review_count = sum(1 for a in scored_articles if a.effective_category.value == "felülvizsgálandó")
            run.noise_count = sum(1 for a in scored_articles if a.effective_category.value == "zaj")
            run.status = "completed"
            run.completed_at = datetime.utcnow()

        except Exception as exc:
            logger.exception("Pipeline hiba: %s", exc)
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.utcnow()
            db.complete_run(run)
            raise

        db.complete_run(run)

    logger.info(
        "Pipeline kész [%s]: %d nyers | %d egyedi | %d rel | %d fv | %d zaj",
        run_id,
        run.total_raw_articles,
        run.total_unique_articles,
        run.relevant_count,
        run.review_count,
        run.noise_count,
    )
    return run, scored_articles, raw_articles
