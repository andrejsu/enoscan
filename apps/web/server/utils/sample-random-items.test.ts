import { describe, expect, it } from 'vitest'
import { zodiacWineProfiles } from '#shared/contracts'
import { sampleRandomItems } from './sample-random-items'

describe('sampleRandomItems', () => {
  it('selects at most three unique recommendations from every zodiac scope', () => {
    for (const profile of zodiacWineProfiles) {
      const scope = profile.catalogQueries.flatMap((query, queryIndex) =>
        Array.from({ length: 4 }, (_, wineIndex) => `${queryIndex}-${wineIndex}-${query}`),
      )

      const recommendations = sampleRandomItems(scope, 3, () => 0.5)

      expect(recommendations).toHaveLength(3)
      expect(new Set(recommendations)).toHaveLength(3)
      expect(recommendations.every(item => scope.includes(item))).toBe(true)
    }
  })

  it('can produce different selections without changing the source scope', () => {
    const scope = ['a', 'b', 'c', 'd', 'e']

    const first = sampleRandomItems(scope, 3, () => 0)
    const second = sampleRandomItems(scope, 3, () => 0.99)

    expect(first).not.toEqual(second)
    expect(scope).toEqual(['a', 'b', 'c', 'd', 'e'])
  })
})
