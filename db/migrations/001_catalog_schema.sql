DROP VIEW IF EXISTS wine_catalog;
DROP TABLE IF EXISTS wine_catalog_raw, wine_media, dataset_imports;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE import_runs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  dataset_version text NOT NULL,
  catalog_sha256 text NOT NULL,
  archive_sha256 text NOT NULL,
  overrides_sha256 text NOT NULL,
  mapping_algo_version text NOT NULL,
  preview_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
  stats jsonb NOT NULL DEFAULT '{}',
  error text,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);
CREATE UNIQUE INDEX import_runs_succeeded_version_idx ON import_runs (dataset_version) WHERE status = 'succeeded';

CREATE TABLE catalog_rows_raw (
  run_id bigint NOT NULL REFERENCES import_runs (id) ON DELETE CASCADE,
  row_no integer NOT NULL,
  payload jsonb NOT NULL,
  PRIMARY KEY (run_id, row_no)
);

CREATE TABLE wines (
  slug text PRIMARY KEY,
  name text,
  category text,
  color text,
  region text,
  grape_varieties text[] NOT NULL DEFAULT '{}',
  description text,
  winery text,
  source_image_filename text,
  source_row_no integer NOT NULL,
  raw_record_count integer NOT NULL,
  is_active boolean NOT NULL,
  first_seen_run_id bigint NOT NULL REFERENCES import_runs (id),
  updated_run_id bigint NOT NULL REFERENCES import_runs (id)
);

CREATE TABLE images (
  sha256 text PRIMARY KEY,
  object_key text NOT NULL UNIQUE,
  preview_key text NOT NULL UNIQUE,
  mime text NOT NULL,
  width integer NOT NULL,
  height integer NOT NULL,
  size_bytes bigint NOT NULL,
  preview_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE image_sources (
  strapi_path text PRIMARY KEY,
  filename text NOT NULL,
  image_sha256 text NOT NULL REFERENCES images (sha256),
  archive_sha256 text NOT NULL
);
CREATE INDEX image_sources_sha_idx ON image_sources (image_sha256);

CREATE TABLE wine_images (
  slug text NOT NULL REFERENCES wines (slug),
  image_sha256 text NOT NULL REFERENCES images (sha256),
  strapi_path text NOT NULL REFERENCES image_sources (strapi_path),
  is_primary boolean NOT NULL,
  mapping_kind text NOT NULL CHECK (mapping_kind IN ('image_filename', 'slug', 'fuzzy_filename', 'manual')),
  mapping_score real NOT NULL,
  review_status text NOT NULL CHECK (review_status IN ('auto', 'suspicious', 'confirmed')),
  run_id bigint NOT NULL REFERENCES import_runs (id),
  PRIMARY KEY (slug, image_sha256)
);
CREATE UNIQUE INDEX wine_images_primary_idx ON wine_images (slug) WHERE is_primary;
CREATE INDEX wine_images_sha_idx ON wine_images (image_sha256);

CREATE TABLE image_overrides (
  line_no integer PRIMARY KEY,
  slug text NOT NULL,
  action text NOT NULL CHECK (action IN ('set', 'reject', 'confirm')),
  strapi_filename text,
  note text,
  run_id bigint NOT NULL REFERENCES import_runs (id)
);

CREATE TABLE import_issues (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES import_runs (id) ON DELETE CASCADE,
  kind text NOT NULL,
  slug text,
  detail jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX import_issues_run_kind_idx ON import_issues (run_id, kind);

CREATE TABLE index_builds (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  kind text NOT NULL,
  dataset_version text NOT NULL,
  object_key text NOT NULL,
  reference_count integer NOT NULL,
  built_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (kind, dataset_version)
);

CREATE TABLE index_references (
  build_id bigint NOT NULL REFERENCES index_builds (id) ON DELETE CASCADE,
  position integer NOT NULL,
  slug text NOT NULL REFERENCES wines (slug),
  image_sha256 text NOT NULL REFERENCES images (sha256),
  PRIMARY KEY (build_id, position),
  UNIQUE (build_id, slug)
);

CREATE TABLE image_embeddings (
  image_sha256 text NOT NULL REFERENCES images (sha256),
  model text NOT NULL,
  embedding vector(384) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (image_sha256, model)
);
