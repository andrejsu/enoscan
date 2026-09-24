import { describe, expect, it } from 'vitest'
import type { ScanDebug } from '#shared/contracts'
import { cropBoxStyle, firstFieldWithCandidates, formatScore, rankingSegments, scanDebugStages } from './scan-debug'

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
  ranking: { durationMs: 4, status: 'not_found', score: 0.3, threshold: 0.45, candidates: [] },
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
    ])
    expect(segments.map(segment => segment.field)).toEqual(['name', 'slug'])
    const total = segments.reduce((sum, segment) => sum + segment.contribution, 0)
    expect(total).toBeCloseTo((0.3 * 1 + 0.2 * 0.5) / 0.7)
  })

  it('returns no segments without evidence', () => {
    expect(rankingSegments([])).toEqual([])
  })

  it('opens the OCR block on the first field that has candidates', () => {
    expect(firstFieldWithCandidates(debug.ocr.fields)).toBe('winery')
  })

  it('flags the failing stages of a scan', () => {
    const stages = scanDebugStages(debug)
    expect(stages.map(stage => stage.key)).toEqual(['preprocessing', 'ocr', 'retriever', 'ranking'])
    expect(stages.map(stage => stage.hasProblem)).toEqual([false, false, true, true])
    expect(stages[2]?.summary).toContain('ConnectTimeout')
    expect(stages[3]?.summary).toBe('0.300 ≤ 0.450')
  })
})
