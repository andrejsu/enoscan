import { describe, expect, it } from 'vitest'
import { detectPairingTastes, extractPairingSubject, pairingLocation, parsePairingTastes, restorePairing, restorePairingWine } from './pairings'

const wine = {
  slug: 'riesling',
  name: 'Рислинг',
  producer: 'Винодельня',
  year: 2022,
  color: 'Белое',
  region: 'Крым',
  imagePreviewUrl: '/api/wines/riesling/image?size=preview',
}
const legacyWine = { slug: 'riesling', name: 'Рислинг', producer: 'Винодельня' }

describe('extractPairingSubject', () => {
  it('keeps the dish or occasion from a sommelier question', () => {
    expect(extractPairingSubject('Подбери вино к запечённой рыбе')).toBe('к запечённой рыбе')
    expect(extractPairingSubject('Что выбрать для праздничного аперитива?')).toBe('для праздничного аперитива')
    expect(extractPairingSubject('А что к стейку?')).toBe('к стейку')
  })

  it('returns nothing when the question names no pairing', () => {
    expect(extractPairingSubject('Что посоветуешь?')).toBe('')
  })
})

describe('detectPairingTastes', () => {
  it('finds tastes in the reply and keeps catalog order', () => {
    expect(detectPairingTastes('Свежий рислинг, сухой, с минеральностью')).toEqual(['Сухое', 'Свежее', 'Минеральное'])
  })

  it('does not mistake semi-sweet for sweet', () => {
    expect(detectPairingTastes('Полусладкое белое', null)).toEqual(['Полусладкое'])
  })
})

describe('pairingLocation', () => {
  const wineQuery = {
    ...legacyWine,
    year: '2022',
    color: 'Белое',
    region: 'Крым',
    image: '/api/wines/riesling/image?size=preview',
  }

  it('passes the wine card and only known context to the form', () => {
    expect(pairingLocation(wine, { pairing: 'к рыбе', tastes: ['Сухое', 'Свежее'] }).query)
      .toEqual({ ...wineQuery, pairing: 'к рыбе', tastes: 'Сухое,Свежее' })
    expect(pairingLocation(wine).query).toEqual(wineQuery)
  })

  it('round-trips through the form query', () => {
    expect(restorePairingWine(pairingLocation(wine).query)).toEqual(wine)
  })
})

describe('parsePairingTastes', () => {
  it('drops unknown values from the query', () => {
    expect(parsePairingTastes('Сухое,<script>,Пряное')).toEqual(['Сухое', 'Пряное'])
    expect(parsePairingTastes(42)).toEqual([])
  })
})

describe('restorePairingWine', () => {
  it('drops images outside the catalog and impossible years', () => {
    expect(restorePairingWine({ ...legacyWine, image: 'https://evil.example/x.png', year: '12' }))
      .toEqual({ ...legacyWine, year: null, color: null, region: null, imagePreviewUrl: null })
  })

  it('needs a slug and a name', () => {
    expect(restorePairingWine({ name: 'Рислинг' })).toBeNull()
  })
})

describe('restorePairing', () => {
  it('keeps the dish of a v1 record as its pairing', () => {
    expect(restorePairing({
      id: '1',
      wine: legacyWine,
      dish: 'Стейк',
      preference: 'richer',
      verdict: 'Хорошее сочетание',
      savedAt: '2026-09-27T00:00:00.000Z',
    })).toEqual({
      id: '1',
      wine: { ...legacyWine, year: null, color: null, region: null, imagePreviewUrl: null },
      pairing: 'Стейк',
      tastes: [],
      savedAt: '2026-09-27T00:00:00.000Z',
    })
  })

  it('rejects records without a wine or with a broken date', () => {
    expect(restorePairing({ id: '1', pairing: 'к рыбе', tastes: [], savedAt: '2026-09-27T00:00:00.000Z' })).toBeNull()
    expect(restorePairing({ id: '1', wine, pairing: 'к рыбе', tastes: [], savedAt: 'вчера' })).toBeNull()
  })
})
