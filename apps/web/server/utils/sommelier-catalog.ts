import type { CatalogSearchFilters, WineCard } from '#shared/contracts'

import { getCatalogPool } from './catalog-db'
import { wineImageUrls } from './wine-images'

interface CatalogRow {
  slug: string
  name: string | null
  category: string | null
  color: string | null
  region: string | null
  grape_varieties: string[]
  description: string | null
  winery: string | null
  has_image: boolean
}

const GRAPES_TEXT = `array_to_string(w.grape_varieties, ', ')`

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

export function toWineCard(row: CatalogRow): WineCard {
  const year = row.name?.match(/(?<!\d)(19\d{2}|20\d{2})(?!\d)/)?.[1]

  return {
    slug: row.slug,
    name: row.name?.trim() || 'Без названия',
    producer: row.winery?.trim() || 'Производитель не указан',
    year: year ? Number.parseInt(year, 10) : null,
    category: row.category?.trim() || null,
    color: row.color?.trim() || null,
    region: row.region?.trim() || null,
    grapeVarieties: row.grape_varieties.map(item => item.trim()).filter(Boolean),
    description: row.description?.trim() || null,
    servingTemperature: null,
    ...wineImageUrls(row.slug, row.has_image),
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
  const values: unknown[] = []
  const conditions: string[] = ['w.is_active']
  addContainsCondition(conditions, values, 'w.color', filters.color)
  addContainsCondition(conditions, values, 'w.region', filters.region)
  addContainsCondition(conditions, values, GRAPES_TEXT, filters.grapeVariety)
  addContainsCondition(conditions, values, 'w.category', filters.category)

  if (filters.occasionKeywords?.length) {
    const keywordConditions = filters.occasionKeywords.map((keyword) => {
      values.push(keyword)
      return `to_tsvector('russian', concat_ws(' ', w.name, w.category, w.color, w.region, ${GRAPES_TEXT}, w.description, w.winery)) @@ plainto_tsquery('russian', $${values.length})`
    })
    conditions.push(`(${keywordConditions.join(' OR ')})`)
  }

  values.push(filters.limit)
  const result = await getCatalogPool(databaseUrl).query<CatalogRow>(
    `
      SELECT w.slug, w.name, w.category, w.color, w.region, w.grape_varieties, w.description, w.winery,
        wi.slug IS NOT NULL AS has_image
      FROM wines w
      LEFT JOIN wine_images wi ON wi.slug = w.slug AND wi.is_primary
      WHERE ${conditions.join(' AND ')}
      ORDER BY
        CASE WHEN w.description IS NULL OR btrim(w.description) = '' THEN 1 ELSE 0 END,
        w.winery,
        w.name,
        w.slug
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
