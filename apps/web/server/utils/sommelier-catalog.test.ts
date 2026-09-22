import type { CatalogSearchFilters } from '#shared/contracts'
import { describe, expect, it } from 'vitest'

import { buildCatalogSearchAttempts } from './sommelier-catalog'

describe('sommelier catalog search attempts', () => {
  it('retries without descriptive keywords while preserving structured preferences', () => {
    const filters: CatalogSearchFilters = {
      category: 'Белое',
      occasionKeywords: ['фруктовый', 'минеральный'],
      limit: 5,
    }

    expect(buildCatalogSearchAttempts(filters)).toEqual([
      filters,
      { category: 'Белое', limit: 5 },
    ])
  })

  it('does not fall back to an unfiltered catalog query', () => {
    const filters: CatalogSearchFilters = {
      occasionKeywords: ['фруктовый'],
      limit: 5,
    }

    expect(buildCatalogSearchAttempts(filters)).toEqual([filters])
  })
})
