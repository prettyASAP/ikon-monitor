-- IKO Monitor – Schema Migration v003
-- 1. FTS5 DELETE trigger (v002-ből hiányzott)
-- 2. FTS index rebuild (duplikátumok eltávolítása)
-- 3. UNIQUE partial index: egyszerre csak egy 'running' futás
-- Idempotens: IF NOT EXISTS / OR IGNORE védelmek

-- ── FTS5 DELETE trigger ───────────────────────────────────────────────────────
-- INSERT OR REPLACE INTO articles SQLite-ban DELETE+INSERT sorozatként fut.
-- A v002 update-trigger törli a régi FTS sort, de a DELETE trigger hiányzott,
-- ezért minden újrafuttatás után duplikált FTS bejegyzések keletkeztek.
CREATE TRIGGER IF NOT EXISTS articles_fts_delete
AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts (articles_fts, rowid, article_id, run_id, title, excerpt)
    VALUES ('delete', old.rowid, old.article_id, old.run_id,
            COALESCE(old.title, ''), COALESCE(old.excerpt, ''));
END;

-- ── FTS rebuild: meglévő duplikátumok eltávolítása ───────────────────────────
INSERT INTO articles_fts(articles_fts) VALUES ('rebuild');

-- ── Race condition fix: partial unique index ──────────────────────────────────
-- Ha két egyidejű API kérés érkezik trigger_run-ra, az INSERT UNIQUE constraintet
-- dob (IntegrityError), amit a router 409-ként kezel.
CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_single_running
    ON pipeline_runs(status) WHERE status = 'running';

-- ── Migration lezárása ────────────────────────────────────────────────────────
INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (3, datetime('now'), 'fts5 delete trigger + fts rebuild + single-running index');
