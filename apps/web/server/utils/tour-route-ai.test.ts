import type { TourRouteDraft } from '#shared/contracts'
import { describe, expect, it } from 'vitest'

import { resolveTourRouteDraft } from './tour-route-ai'

const draft: TourRouteDraft = {
  message: 'Собрал маршрут.',
  title: 'Крым на выходные',
  summary: 'Две разные точки без спешки.',
  tourIds: ['golden-balka-intro', 'winepark-intro'],
  days: 2,
}

describe('tour route grounding', () => {
  it('derives the price from trusted catalog tours', () => {
    expect(resolveTourRouteDraft(draft)).toEqual({
      title: 'Крым на выходные',
      summary: 'Две разные точки без спешки.',
      tourIds: ['golden-balka-intro', 'winepark-intro'],
      days: 2,
      estimatedPricePerPerson: 4300,
    })
  })

  it('deduplicates repeated tour ids', () => {
    expect(resolveTourRouteDraft({
      ...draft,
      tourIds: ['golden-balka-intro', 'golden-balka-intro'],
    })?.tourIds).toEqual(['golden-balka-intro'])
  })

  it('rejects a tour id outside the catalog', () => {
    expect(resolveTourRouteDraft({ ...draft, tourIds: ['invented-tour'] })).toBeNull()
  })
})
