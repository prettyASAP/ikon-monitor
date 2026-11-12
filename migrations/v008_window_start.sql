-- Migration v008: a futás pontos időablak-kezdete (UTC ISO), a munkanapos napi gyűjtéshez

BEGIN TRANSACTION;

ALTER TABLE pipeline_runs ADD COLUMN window_start TEXT;

INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (8, datetime('now'), 'window_start: munkanapos időablak kezdete');

COMMIT;
