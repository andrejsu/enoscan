import type { ScanRecommendation, WineCard } from '#shared/contracts'
import { describe, expect, it } from 'vitest'
import { visibleRecommendations } from './scan-recommendations'

const wine: WineCard = {
  slug: 'inkerman-shato-ruzh',
  name: 'Inkerman Шато Руж',
  producer: 'Инкерманский ЗМВ',
  year: null,
  category: 'Красное',
  color: 'Красное',
  region: 'Крым',
  grapeVarieties: ['Каберне Совиньон'],
  description: null,
  servingTemperature: null,
  imageUrl: null,
  imagePreviewUrl: null,
}

function recommendation(slug: string): ScanRecommendation {
  return { slug, score: 0.3, wine: { ...wine, slug }, sharedFields: ['winery'], reason: 'Та же винодельня', difference: null }
}

describe('visibleRecommendations', () => {
  it('offers related wines when the scan found nothing', () => {
    const recommendations = [recommendation('a'), recommendation('b')]
    expect(visibleRecommendations({ status: 'not_found', recommendations })).toEqual(recommendations)
  })

  it('shows at most three', () => {
    const recommendations = ['a', 'b', 'c', 'd'].map(recommendation)
    expect(visibleRecommendations({ status: 'not_found', recommendations })).toHaveLength(3)
  })

  it('never mixes alternatives into a confirmed match', () => {
    expect(visibleRecommendations({ status: 'matched', recommendations: [recommendation('a')] })).toEqual([])
  })

  it('handles services that do not recommend', () => {
    expect(visibleRecommendations({ status: 'not_found' })).toEqual([])
  })
})
