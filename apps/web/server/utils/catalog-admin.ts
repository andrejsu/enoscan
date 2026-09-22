import type {
  CatalogAdminResponse,
  CatalogAdminWine,
  CatalogImageStatus,
  CatalogMappingKind,
  CatalogReviewStatus,
  CatalogSummary,
} from '#shared/contracts'
import { catalogImageStatuses } from '#shared/contracts'
import type { Pool } from 'pg'

import { wineImageUrls } from './wine-images'

export const ADMIN_PAGE_SIZE = 24
export const ADMIN_QUERY_MAX_LENGTH = 120
export const SEARCH_INDEX_KIND = 'sift-v3'

export interface AdminQuery {
  q: string
  page: number
  imageStatus: CatalogImageStatus
}

interface AdminRow {
  slug: string
  name: string | null
  winery: string | null
  category: string | null
  color: string | null
  region: string | null
  grape_varieties: string[]
  description: string | null
  source_image_filename: string | null
  raw_record_count: number
  strapi_path: string | null
  mapping_kind: CatalogMappingKind | null
  mapping_score: number | null
  review_status: CatalogReviewStatus | null
  is_indexed: boolean
  total_count: string
}

interface SummaryRow {
  dataset_version: string
  finished_at: Date
  stats: { catalog_rows?: number, duplicate_slugs?: number }
  unique_wines: string
  inactive_wines: string
  images: string
  orphan_images: string
  wines_with_image: string
  suspicious_mappings: string
  indexed_wines: string
}

export function parseAdminQuery(query: Record<string, unknown>): AdminQuery {
  const rawPage = typeof query.page === 'string' ? Number.parseInt(query.page, 10) : 1
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1
  const q = typeof query.q === 'string' ? query.q.trim().slice(0, ADMIN_QUERY_MAX_LENGTH) : ''
  const imageStatus = catalogImageStatuses.find(status => status === query.imageStatus) ?? 'all'
  return { q, page, imageStatus }
}

const imageStatusConditions: Record<CatalogImageStatus, string | null> = {
  all: null,
  with_image: 'wi.slug IS NOT NULL',
  without_image: 'wi.slug IS NULL',
  suspicious: `wi.review_status = 'suspicious'`,
  not_indexed: 'NOT EXISTS (SELECT 1 FROM index_references ir WHERE ir.build_id = current_build.id AND ir.slug = w.slug)',
}

const CURRENT_BUILD = `
  current_run AS (
    SELECT dataset_version FROM import_runs WHERE status = 'succeeded' ORDER BY id DESC LIMIT 1
  ),
  current_build AS (
    SELECT (
      SELECT b.id FROM index_builds b JOIN current_run r USING (dataset_version)
      WHERE b.kind = '${SEARCH_INDEX_KIND}'
    ) AS id
  )
`

function toAdminWine(row: AdminRow): CatalogAdminWine {
  const year = row.name?.match(/(?<!\d)(19\d{2}|20\d{2})(?!\d)/)?.[1]
  return {
    slug: row.slug,
    name: row.name?.trim() || 'Без названия',
    producer: row.winery?.trim() || 'Производитель не указан',
    year: year ? Number.parseInt(year, 10) : null,
    category: row.category,
    color: row.color,
    region: row.region,
    grapeVarieties: row.grape_varieties,
    description: row.description,
    servingTemperature: null,
    ...wineImageUrls(row.slug, row.strapi_path !== null),
    sourceImageFilename: row.source_image_filename,
    imageStrapiPath: row.strapi_path,
    mappingKind: row.mapping_kind,
    mappingScore: row.mapping_score === null ? null : Math.round(row.mapping_score * 10_000) / 10_000,
    reviewStatus: row.review_status,
    rawRecordCount: row.raw_record_count,
    isIndexed: row.is_indexed,
  }
}

async function loadSummary(pool: Pool): Promise<CatalogSummary | null> {
  const result = await pool.query<SummaryRow>(`
    WITH ${CURRENT_BUILD}
    SELECT
      r.dataset_version,
      r.finished_at,
      r.stats,
      (SELECT count(*) FROM wines WHERE is_active) AS unique_wines,
      (SELECT count(*) FROM wines WHERE NOT is_active) AS inactive_wines,
      (SELECT count(DISTINCT image_sha256) FROM image_sources) AS images,
      (SELECT count(DISTINCT s.image_sha256) FROM image_sources s
        WHERE NOT EXISTS (SELECT 1 FROM wine_images wi WHERE wi.image_sha256 = s.image_sha256)) AS orphan_images,
      (SELECT count(*) FROM wine_images wi JOIN wines w ON w.slug = wi.slug AND w.is_active
        WHERE wi.is_primary) AS wines_with_image,
      (SELECT count(*) FROM wine_images WHERE review_status = 'suspicious') AS suspicious_mappings,
      (SELECT count(*) FROM index_references ir, current_build cb WHERE ir.build_id = cb.id) AS indexed_wines
    FROM import_runs r
    WHERE r.status = 'succeeded'
    ORDER BY r.id DESC
    LIMIT 1
  `)
  const row = result.rows[0]
  if (!row) return null
  return {
    datasetVersion: row.dataset_version,
    importedAt: row.finished_at.toISOString(),
    rawRecords: row.stats.catalog_rows ?? 0,
    uniqueWines: Number(row.unique_wines),
    inactiveWines: Number(row.inactive_wines),
    duplicateSlugs: row.stats.duplicate_slugs ?? 0,
    images: Number(row.images),
    orphanImages: Number(row.orphan_images),
    winesWithImage: Number(row.wines_with_image),
    suspiciousMappings: Number(row.suspicious_mappings),
    indexedWines: Number(row.indexed_wines),
  }
}

async function loadWines(pool: Pool, query: AdminQuery): Promise<{ wines: CatalogAdminWine[], total: number }> {
  const values: unknown[] = []
  const conditions = ['w.is_active']
  if (query.q) {
    values.push(`%${query.q}%`)
    conditions.push(`concat_ws(' ', w.slug, w.name, w.winery, w.category, w.color, w.region,
      array_to_string(w.grape_varieties, ' ')) ILIKE $${values.length}`)
  }
  const statusCondition = imageStatusConditions[query.imageStatus]
  if (statusCondition) conditions.push(statusCondition)
  values.push(ADMIN_PAGE_SIZE, (query.page - 1) * ADMIN_PAGE_SIZE)

  const result = await pool.query<AdminRow>(
    `
      WITH ${CURRENT_BUILD}
      SELECT
        w.slug, w.name, w.winery, w.category, w.color, w.region, w.grape_varieties, w.description,
        w.source_image_filename, w.raw_record_count,
        wi.strapi_path, wi.mapping_kind, wi.mapping_score, wi.review_status,
        EXISTS (
          SELECT 1 FROM index_references ir WHERE ir.build_id = current_build.id AND ir.slug = w.slug
        ) AS is_indexed,
        count(*) OVER () AS total_count
      FROM wines w
      CROSS JOIN current_build
      LEFT JOIN wine_images wi ON wi.slug = w.slug AND wi.is_primary
      WHERE ${conditions.join(' AND ')}
      ORDER BY w.winery NULLS LAST, w.name NULLS LAST, w.slug
      LIMIT $${values.length - 1} OFFSET $${values.length}
    `,
    values,
  )
  return {
    wines: result.rows.map(toAdminWine),
    total: result.rows[0] ? Number(result.rows[0].total_count) : 0,
  }
}

export async function browseCatalog(pool: Pool, query: AdminQuery): Promise<CatalogAdminResponse | null> {
  const summary = await loadSummary(pool)
  if (!summary) return null
  const { wines, total } = await loadWines(pool, query)
  return {
    summary,
    wines,
    pagination: {
      page: query.page,
      perPage: ADMIN_PAGE_SIZE,
      totalItems: total,
      totalPages: total ? Math.ceil(total / ADMIN_PAGE_SIZE) : 0,
    },
  }
}
