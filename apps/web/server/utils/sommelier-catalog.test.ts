import type { CatalogSearchFilters } from '#shared/contracts'
import { describe, expect, it } from 'vitest'

import { buildCatalogSearchAttempts, toWineCard } from './sommelier-catalog'

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

describe('sommelier catalog cards', () => {
  const row = {
    slug: 'kokur-2020',
    name: ' Кокур 2020 ',
    category: null,
    color: 'Белое',
    region: null,
    grape_varieties: ['Кокур', ' '],
    description: '',
    winery: null,
    has_image: true,
  }

  it('maps grape arrays and image urls from the mapping', () => {
    expect(toWineCard(row)).toMatchObject({
      name: 'Кокур 2020',
      producer: 'Производитель не указан',
      year: 2020,
      grapeVarieties: ['Кокур'],
      description: null,
      imageUrl: '/api/wines/kokur-2020/image',
      imagePreviewUrl: '/api/wines/kokur-2020/image?size=preview',
    })
  })

  it('does not promise an image when the wine has no mapping', () => {
    expect(toWineCard({ ...row, has_image: false })).toMatchObject({ imageUrl: null, imagePreviewUrl: null })
  })
})
