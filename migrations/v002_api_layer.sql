-- IKO Monitor – Schema Migration v002: API Layer
-- Idempotens: BEGIN/COMMIT egységbe zárva, schema_version tábla véd a dupla futástól.
-- Futtatja: ikon/database.py run_migrations()

PRAGMA foreign_keys = ON;
BEGIN;

-- ── Schema verziókövetés ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL,
    description TEXT
);
INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (1, datetime('now'), 'initial DDL (retroactive)');

-- ── feedback: reviewer attribúció + audit timestamps ─────────────────────────
ALTER TABLE feedback ADD COLUMN reviewer_id  TEXT DEFAULT NULL;
ALTER TABLE feedback ADD COLUMN created_at   TEXT DEFAULT NULL;
ALTER TABLE feedback ADD COLUMN updated_at   TEXT DEFAULT NULL;

-- Backfill: meglévő soroknál reviewed_at adja az audit időpontot
UPDATE feedback
SET created_at = reviewed_at,
    updated_at = reviewed_at
WHERE created_at IS NULL;

-- ── pipeline_runs: trigger forrás + config snapshot ──────────────────────────
ALTER TABLE pipeline_runs ADD COLUMN triggered_by    TEXT DEFAULT 'cli';
ALTER TABLE pipeline_runs ADD COLUMN config_snapshot TEXT DEFAULT NULL;

-- ── articles: ISO dátumoszlop range query-khez ───────────────────────────────
-- YYYY.MM.DD → YYYY-MM-DD (SQLite nem tudja indexelni a pont-formátumot jól)
ALTER TABLE articles ADD COLUMN published_date_iso TEXT DEFAULT NULL;

UPDATE articles
SET published_date_iso =
    SUBSTR(published_date, 1, 4) || '-' ||
    SUBSTR(published_date, 6, 2) || '-' ||
    SUBSTR(published_date, 9, 2)
WHERE published_date IS NOT NULL
  AND published_date LIKE '____.__.__';

-- ── keywords: DB-driven kulcsszó-kezelés ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS keywords (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword    TEXT NOT NULL UNIQUE,
    tier       TEXT NOT NULL CHECK(tier IN ('tier1_specifikus', 'tier2_kozepes', 'tier3_generikus')),
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── scoring_configs: verzionált scoring paraméter snapshots ──────────────────
CREATE TABLE IF NOT EXISTS scoring_configs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    config_json TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 0 CHECK(is_active IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    notes       TEXT DEFAULT NULL
);

-- ── FTS5: teljes szöveges keresés (title + excerpt) ─────────────────────────
-- unicode61 tokenizer: ékezetes karaktereket helyesen kezeli
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    article_id UNINDEXED,
    run_id     UNINDEXED,
    title,
    excerpt,
    content    = 'articles',
    content_rowid = 'rowid',
    tokenize   = 'unicode61'
);

-- Meglévő cikkek indexelése
INSERT INTO articles_fts (rowid, article_id, run_id, title, excerpt)
SELECT rowid, article_id, run_id,
       COALESCE(title, ''),
       COALESCE(excerpt, '')
FROM articles;

-- FTS szinkronizáló triggerek (új insert / update esetén)
CREATE TRIGGER IF NOT EXISTS articles_fts_insert
AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts (rowid, article_id, run_id, title, excerpt)
    VALUES (new.rowid, new.article_id, new.run_id,
            COALESCE(new.title, ''), COALESCE(new.excerpt, ''));
END;

CREATE TRIGGER IF NOT EXISTS articles_fts_update
AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts (articles_fts, rowid, article_id, run_id, title, excerpt)
    VALUES ('delete', old.rowid, old.article_id, old.run_id,
            COALESCE(old.title, ''), COALESCE(old.excerpt, ''));
    INSERT INTO articles_fts (rowid, article_id, run_id, title, excerpt)
    VALUES (new.rowid, new.article_id, new.run_id,
            COALESCE(new.title, ''), COALESCE(new.excerpt, ''));
END;

-- ── Új indexek ────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_articles_date_iso
    ON articles (published_date_iso DESC);

CREATE INDEX IF NOT EXISTS idx_articles_run_cat
    ON articles (run_id, category);

CREATE INDEX IF NOT EXISTS idx_articles_tier
    ON articles (best_tier);

CREATE INDEX IF NOT EXISTS idx_articles_source_type
    ON articles (source_type);

CREATE INDEX IF NOT EXISTS idx_feedback_reviewed
    ON feedback (reviewed_at DESC);

CREATE INDEX IF NOT EXISTS idx_keywords_tier_active
    ON keywords (tier, is_active);

CREATE INDEX IF NOT EXISTS idx_pipeline_status
    ON pipeline_runs (status, started_at DESC);

-- ── Migration lezárása ────────────────────────────────────────────────────────
INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (2, datetime('now'), 'api layer: keywords, scoring_configs, articles_fts, audit columns');

COMMIT;
