-- IKO Monitor – Schema Migration v004
-- Kulcsszó profilok: 'iko_ceg' és 'tv_radio_musorok'
-- Idempotens: IF NOT EXISTS / OR IGNORE védelmek

PRAGMA foreign_keys = ON;

-- ── keywords: profile oszlop ─────────────────────────────────────────────────
-- SQLite nem támogatja az ADD COLUMN IF NOT EXISTS-t, ezért a hibaelhárítás
-- a database.py run_migrations() szintjén történik (executescript try/catch).
-- Az oszlop alapértelmezésben 'iko_ceg' – a meglévő kulcsszavak változatlanok.
ALTER TABLE keywords ADD COLUMN profile TEXT NOT NULL DEFAULT 'iko_ceg';

-- ── pipeline_runs: keyword_profile oszlop ────────────────────────────────────
ALTER TABLE pipeline_runs ADD COLUMN keyword_profile TEXT DEFAULT 'iko_ceg';

-- ── Meglévő futások visszamenőleges megjelölése ───────────────────────────────
UPDATE pipeline_runs SET keyword_profile = 'iko_ceg' WHERE keyword_profile IS NULL;

-- ── Index ────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_keywords_profile_active ON keywords(profile, is_active);
CREATE INDEX IF NOT EXISTS idx_runs_profile ON pipeline_runs(keyword_profile, started_at DESC);

-- ── Migration lezárása ────────────────────────────────────────────────────────
INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (4, datetime('now'), 'keyword profiles: iko_ceg, tv_radio_musorok');
