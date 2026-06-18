-- IKO Monitor – Schema Migration v005
-- keywords UNIQUE constraint: (keyword) → (keyword, profile)
-- Lehetővé teszi ugyanazt a kulcsszót több profilban párhuzamosan

PRAGMA foreign_keys = OFF;
BEGIN;

-- ── keywords tábla újraépítése új UNIQUE-kulccsal ────────────────────────────
CREATE TABLE keywords_new (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword    TEXT NOT NULL,
    tier       TEXT NOT NULL CHECK(tier IN ('tier1_specifikus', 'tier2_kozepes', 'tier3_generikus')),
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    profile    TEXT NOT NULL DEFAULT 'iko_ceg',
    UNIQUE(keyword, profile)
);

INSERT INTO keywords_new (id, keyword, tier, is_active, created_at, updated_at, profile)
SELECT id, keyword, tier, is_active, created_at, updated_at, profile FROM keywords;

DROP TABLE keywords;
ALTER TABLE keywords_new RENAME TO keywords;

CREATE INDEX IF NOT EXISTS idx_keywords_tier_active    ON keywords(tier, is_active);
CREATE INDEX IF NOT EXISTS idx_keywords_profile_active ON keywords(profile, is_active);

-- ── Új NAPI kulcsszavak ──────────────────────────────────────────────────────
-- Korábban iko_ceg profilban UNIQUE-konfliktus miatt ki lettek zárva.
-- Az új (keyword, profile) egyediség után mindkét profilban létezhetnek.
INSERT OR IGNORE INTO keywords (keyword, tier, profile) VALUES
    -- T1: Media Vivantis tulajdonos
    ('Vaszily Miklós',           'tier1_specifikus', 'napi'),
    -- T2: médiaipari személyek + brandelt tartalom-kategóriák
    ('Kovács Gergely',           'tier2_kozepes',    'napi'),
    ('Nielsen közönségmérés',    'tier2_kozepes',    'napi'),
    ('klasszikus sorozat',       'tier2_kozepes',    'napi'),
    ('televíziós legenda',       'tier2_kozepes',    'napi'),
    -- T3: általános médiaipari kifejezések
    ('nézettség',                'tier3_generikus',  'napi'),
    ('televíziós piac',          'tier3_generikus',  'napi'),
    ('magyar televíziózás',      'tier3_generikus',  'napi'),
    ('médiapiac',                'tier3_generikus',  'napi'),
    ('televíziós reklámpiac',    'tier3_generikus',  'napi'),
    ('csatornaindítás',          'tier3_generikus',  'napi'),
    ('csatorna-megújulás',       'tier3_generikus',  'napi'),
    ('műsorstruktúra',           'tier3_generikus',  'napi'),
    ('nézettségi adatok',        'tier3_generikus',  'napi'),
    ('televíziós közönségarány', 'tier3_generikus',  'napi');

INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (5, datetime('now'), 'keywords UNIQUE: (keyword) → (keyword, profile) + NAPI cross-profile keywords');

COMMIT;
PRAGMA foreign_keys = ON;
