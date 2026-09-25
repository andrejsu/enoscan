import { describe, expect, it } from 'vitest'
import type { ScanDebug, WineCard } from '#shared/contracts'
import { cropBoxStyle, firstFieldWithCandidates, formatScore, rankingMatchLine, rankingSegments, scanDebugStages, verificationVerdict } from './scan-debug'

const debug: ScanDebug = {
  preprocessing: {
    durationMs: 8,
    usedSam: false,
    warnings: ['sam_skipped'],
    cropBox: [0.05, 0.3, 0.95, 0.95],
    images: { source: 'data:,', visual: 'data:,', ocr: 'data:,' },
    metrics: { labelWidth: 512, labelHeight: 380, sharpness: 120, noiseSigma: 1.4, glareFraction: 0.02, isDenoised: false },
  },
  ocr: {
    durationMs: 640,
    passes: ['crop'],
    text: 'Ребус 2019',
    wordCount: 2,
    meanConfidence: 88,
    error: null,
    fields: [
      { field: 'name', weight: 0.3, candidates: [] },
      { field: 'winery', weight: 0.2, candidates: [{ value: 'Дивноморское', score: 0.9 }] },
    ],
  },
  retriever: { durationMs: 900, error: 'ConnectTimeout', candidates: [] },
  verification: { labelCategory: null, labelYear: null, labelSweetness: null, shortlist: [] },
  ranking: { durationMs: 4, status: 'not_found', score: 0.3, margin: 0.02, minMargin: 0.08, candidates: [] },
}

const checkedWine: WineCard = {
  slug: 'anima', name: 'Аристов Anima Millesimato', producer: 'Кубань-Вино', year: null, category: 'Розовое',
  color: null, region: null, grapeVarieties: [], description: null, servingTemperature: null, imageUrl: null,
  imagePreviewUrl: null,
}

describe('scan debug helpers', () => {
  it('formats scores as raw similarity, not percentages', () => {
    expect(formatScore(0.8271)).toBe('0.827')
  })

  it('positions the crop box in percent of the frame', () => {
    expect(cropBoxStyle([0.05, 0.3, 0.95, 0.95])).toEqual({
      left: '5%', top: '30%', width: '90%', height: '65%',
    })
  })

  it('splits a ranking score into per-field parts that add up to it', () => {
    const segments = rankingSegments([
      { field: 'name', weight: 0.3, score: 1 },
      { field: 'winery', weight: 0.2, score: 0 },
      { field: 'slug', weight: 0.2, score: 0.5 },
    ], 0.42)
    expect(segments.map(segment => segment.field)).toEqual(['name', 'slug'])
    const total = segments.reduce((sum, segment) => sum + segment.contribution, 0)
    expect(total).toBeCloseTo(0.42)
    expect(segments[0]?.contribution).toBeCloseTo(0.42 * 0.3 / 0.4)
  })

  it('returns no segments without evidence', () => {
    expect(rankingSegments([], 0)).toEqual([])
  })

  it('puts the match line at the runner-up score plus the minimum margin', () => {
    expect(rankingMatchLine(debug.ranking)).toBeNull()
    const wine: WineCard = {
      slug: 'rebus', name: 'Ребус', producer: 'Дивноморское', year: null, category: null, color: null, region: null,
      grapeVarieties: [], description: null, servingTemperature: null, imageUrl: null, imagePreviewUrl: null,
    }
    const candidates = [0.5, 0.45].map(score => ({ slug: String(score), score, wine, fields: [], rejection: null }))
    expect(rankingMatchLine({ ...debug.ranking, candidates })).toBeCloseTo(0.53)
  })

  it('opens the OCR block on the first field that has candidates', () => {
    expect(firstFieldWithCandidates(debug.ocr.fields)).toBe('winery')
  })

  it('flags the failing stages of a scan', () => {
    const stages = scanDebugStages(debug)
    expect(stages.map(stage => stage.key)).toEqual(['preprocessing', 'ocr', 'retriever', 'verification', 'ranking'])
    expect(stages.map(stage => stage.hasProblem)).toEqual([false, false, true, false, true])
    expect(stages[2]?.summary).toContain('ConnectTimeout')
    expect(stages[3]?.durationMs).toBeNull()
    expect(stages[4]?.summary).toBe('отрыв 0.020 < 0.080')
  })

  it('reads a label check as rejected, confirmed by name words, or neutral', () => {
    const row = { slug: 'a', wine: checkedWine, readWords: [] as string[], contradiction: null, reason: null }
    expect(verificationVerdict(row)).toBe('neutral')
    expect(verificationVerdict({ ...row, readWords: ['Millesimato'] })).toBe('confirmed')
    expect(verificationVerdict({ ...row, readWords: ['Anima'], contradiction: 'category', reason: 'на этикетке Розовое' }))
      .toBe('rejected')
  })

  it('flags a label check that rejects the whole shortlist', () => {
    const rejected = { slug: 'a', wine: checkedWine, readWords: [], contradiction: 'year' as const, reason: 'на этикетке 2024' }
    const stages = scanDebugStages({ ...debug, verification: { labelCategory: null, labelYear: '2024', labelSweetness: null, shortlist: [rejected] } })
    expect(stages[3]).toMatchObject({ summary: 'отклонено 1 из 1', hasProblem: true })
  })
})
