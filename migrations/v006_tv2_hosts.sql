-- IKO Monitor – Schema Migration v006
-- TV2 műsorvezetők hozzáadása a NAPI kulcsszó profilhoz

BEGIN;

INSERT OR IGNORE INTO keywords (keyword, tier, profile) VALUES
    ('Orsovai Reni',    'tier2_kozepes', 'napi'),
    ('Liptai Claudia',  'tier2_kozepes', 'napi'),
    ('Sebestyén Balázs','tier2_kozepes', 'napi'),
    ('Istenes Bence',   'tier2_kozepes', 'napi'),
    ('Sarka Kata',      'tier2_kozepes', 'napi'),
    ('Csobot Adél',     'tier2_kozepes', 'napi');

INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (6, datetime('now'), 'NAPI profil: TV2 műsorvezetők T2 kulcsszavakként');

COMMIT;
