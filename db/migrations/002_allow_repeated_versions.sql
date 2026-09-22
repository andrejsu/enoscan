DROP INDEX IF EXISTS import_runs_succeeded_version_idx;
CREATE INDEX import_runs_status_id_idx ON import_runs (status, id DESC);
