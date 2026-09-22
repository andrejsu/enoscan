import type { WineCard } from '#shared/contracts'
import { describe, expect, it } from 'vitest'

import { resolveSommelierAnswer } from './sommelier-ai'

const wines: WineCard[] = Array.from({ length: 4 }, (_, index) => ({
  slug: `wine-${index + 1}`,
  name: `Вино ${index + 1}`,
  producer: 'Винодельня',
  year: null,
  category: 'Белое',
  color: 'Светло-соломенный',
  region: null,
  grapeVarieties: [],
  description: null,
  servingTemperature: null,
  imageUrl: null,
}))

describe('sommelier answer resolution', () => {
  it('returns catalog wines when a filtered result was ignored by the model', () => {
    const result = resolveSommelierAnswer(
      { message: 'В каталоге ничего нет.', wineSlugs: [] },
      wines,
      { category: 'Белое', limit: 5 },
    )

    expect(result?.recommendations.map(wine => wine.slug)).toEqual(['wine-1', 'wine-2', 'wine-3'])
    expect(result?.message).not.toContain('ничего нет')
  })

  it('keeps a clarification when the search had no meaningful filters', () => {
    const result = resolveSommelierAnswer(
      { message: 'Какой стиль вина вы предпочитаете?', wineSlugs: [] },
      wines,
      { limit: 5 },
    )

    expect(result).toEqual({
      message: 'Какой стиль вина вы предпочитаете?',
      recommendations: [],
    })
  })

  it('rejects a slug that was not returned by the catalog', () => {
    expect(resolveSommelierAnswer(
      { message: 'Попробуйте этот вариант.', wineSlugs: ['invented-wine'] },
      wines,
      { category: 'Белое', limit: 5 },
    )).toBeNull()
  })
})
