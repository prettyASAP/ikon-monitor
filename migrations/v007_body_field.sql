-- Migration v007: body TEXT mező hozzáadása (Argus teljes cikktartalom)

BEGIN TRANSACTION;

ALTER TABLE raw_articles ADD COLUMN body TEXT DEFAULT '';
ALTER TABLE articles     ADD COLUMN body TEXT DEFAULT '';

INSERT OR IGNORE INTO schema_version (version, applied_at, description)
VALUES (7, datetime('now'), 'body TEXT: Argus teljes cikktartalom tárolása');

COMMIT;
