import { describe, expect, it } from 'vitest'
import type { WineCard } from '#shared/contracts'
import { getZodiacWineProfile, matchScanWineToZodiac, matchWineToZodiac } from '#shared/contracts'

const wine: WineCard = {
  slug: 'peppery-syrah',
  name: 'Сира выдержанное',
  producer: 'Тестовая винодельня',
  year: 2022,
  category: 'Красное сухое',
  color: 'Красное',
  region: null,
  grapeVarieties: ['Сира'],
  description: 'Насыщенное и пряное вино с оттенком чёрного перца.',
  servingTemperature: null,
  imageUrl: null,
  imagePreviewUrl: null,
}

describe('zodiac wine profiles', () => {
  it('matches a peppery Syrah with Aries', () => {
    const result = matchWineToZodiac(wine)

    expect(result.profile.id).toBe('aries')
    expect(result.reasons).toContain('сира')
  })

  it('returns a profile only for a supported sign', () => {
    expect(getZodiacWineProfile('pisces')?.name).toBe('Рыбы')
    expect(getZodiacWineProfile('ophiuchus')).toBeUndefined()
  })

  it('assigns a stable sign to every catalog wine even without descriptive characteristics', () => {
    const catalogWine = {
      ...wine,
      name: 'Вино столовое',
      category: null,
      color: null,
      grapeVarieties: [],
      description: null,
    }

    const firstMatch = matchWineToZodiac(catalogWine)
    const secondMatch = matchWineToZodiac(catalogWine)

    expect(firstMatch.profile.id).toBe(secondMatch.profile.id)
    expect(firstMatch.reasons).toHaveLength(2)
  })

  it.each(['uncertain', 'not_found'] as const)('does not assign a sign when scan status is %s', (status) => {
    const result = matchScanWineToZodiac({ status, wine })

    expect(result).toBeNull()
  })

  it('assigns a sign only after the scanner confirms a catalog wine', () => {
    expect(matchScanWineToZodiac({ status: 'matched', wine })?.profile.id).toBe('aries')
    expect(matchScanWineToZodiac({ status: 'matched', wine: null })).toBeNull()
  })
})
