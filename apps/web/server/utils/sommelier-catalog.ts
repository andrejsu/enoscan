import type { CatalogSearchFilters, WineCard } from '#shared/contracts'
import { Pool } from 'pg'

interface CatalogRow {
  slug: string
  name: string | null
  category: string | null
  color: string | null
  region: string | null
  grape_varieties: string | null
  description: string | null
  winery: string | null
  image_filename: string | null
}

let catalogPool: Pool | undefined

function getCatalogPool(databaseUrl: string): Pool {
  catalogPool ??= new Pool({
    connectionString: databaseUrl || undefined,
    max: 5,
    idleTimeoutMillis: 30_000,
  })
  return catalogPool
}

function addContainsCondition(
  conditions: string[],
  values: unknown[],
  column: string,
  value: string | undefined,
) {
  if (!value) return

  values.push(`%${value}%`)
  conditions.push(`${column} ILIKE $${values.length}`)
}

function toWineCard(row: CatalogRow): WineCard {
  const year = row.name?.match(/(?<!\d)(19\d{2}|20\d{2})(?!\d)/)?.[1]

  return {
    slug: row.slug,
    name: row.name?.trim() || 'Без названия',
    producer: row.winery?.trim() || 'Производитель не указан',
    year: year ? Number.parseInt(year, 10) : null,
    category: row.category?.trim() || null,
    color: row.color?.trim() || null,
    region: row.region?.trim() || null,
    grapeVarieties: row.grape_varieties?.split(',').map(item => item.trim()).filter(Boolean) || [],
    description: row.description?.trim() || null,
    servingTemperature: null,
    imageUrl: row.image_filename ? `/api/wines/${encodeURIComponent(row.slug)}/image` : null,
  }
}

export function buildCatalogSearchAttempts(filters: CatalogSearchFilters): CatalogSearchFilters[] {
  const attempts = [filters]
  const hasStructuredFilter = Boolean(
    filters.category || filters.color || filters.region || filters.grapeVariety,
  )

  if (filters.occasionKeywords?.length && hasStructuredFilter) {
    const relaxedFilters = { ...filters }
    delete relaxedFilters.occasionKeywords
    attempts.push(relaxedFilters)
  }

  return attempts
}

async function querySommelierCatalog(
  filters: CatalogSearchFilters,
  databaseUrl: string,
): Promise<CatalogRow[]> {
  const conditions: string[] = []
  const values: unknown[] = []

  addContainsCondition(conditions, values, 'color', filters.color)
  addContainsCondition(conditions, values, 'region', filters.region)
  addContainsCondition(conditions, values, 'grape_varieties', filters.grapeVariety)
  addContainsCondition(conditions, values, 'category', filters.category)

  if (filters.occasionKeywords?.length) {
    const keywordConditions = filters.occasionKeywords.map((keyword) => {
      values.push(keyword)
      return `to_tsvector('russian', concat_ws(' ', name, category, color, region, grape_varieties, description, winery)) @@ plainto_tsquery('russian', $${values.length})`
    })
    conditions.push(`(${keywordConditions.join(' OR ')})`)
  }

  values.push(filters.limit)
  const whereClause = conditions.length ? `WHERE ${conditions.join(' AND ')}` : ''
  const result = await getCatalogPool(databaseUrl).query<CatalogRow>(
    `
      SELECT slug, name, category, color, region, grape_varieties, description, winery, image_filename
      FROM wine_catalog
      ${whereClause}
      ORDER BY
        CASE WHEN description IS NULL OR btrim(description) = '' THEN 1 ELSE 0 END,
        winery,
        name,
        slug
      LIMIT $${values.length}
    `,
    values,
  )

  return result.rows
}

export async function searchSommelierCatalog(
  filters: CatalogSearchFilters,
  databaseUrl: string,
): Promise<WineCard[]> {
  for (const attempt of buildCatalogSearchAttempts(filters)) {
    const rows = await querySommelierCatalog(attempt, databaseUrl)
    if (rows.length) return rows.map(toWineCard)
  }

  return []
}
