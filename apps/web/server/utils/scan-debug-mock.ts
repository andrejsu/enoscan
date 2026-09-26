import type { ScanDebug, ScanStatus, WineCard } from '#shared/contracts'

function placeholderImage(label: string, width: number, height: number, fill: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">`
    + `<rect width="100%" height="100%" fill="${fill}"/>`
    + `<text x="50%" y="50%" font-family="sans-serif" font-size="20" fill="#fff" text-anchor="middle">${label}</text></svg>`
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`
}

export function createMockScanDebug(status: ScanStatus, wines: readonly WineCard[]): ScanDebug {
  const [first, second] = wines
  const topScore = status === 'matched' ? 0.714 : 0.44
  const secondScore = status === 'matched' ? 0.136 : 0.41

  return {
    preprocessing: {
      durationMs: 9,
      usedSam: false,
      warnings: ['sam_skipped'],
      cropBox: [0.05, 0.3, 0.95, 0.95],
      images: {
        source: placeholderImage('кадр', 300, 400, '#54595f'),
        visual: placeholderImage('visual', 360, 260, '#72090c'),
        ocr: placeholderImage('ocr', 360, 260, '#1a1a1a'),
      },
      metrics: { labelWidth: 512, labelHeight: 370, sharpness: 184, noiseSigma: 1.62, glareFraction: 0.018, isDenoised: false },
    },
    ocr: {
      durationMs: 612,
      passes: ['crop'],
      text: 'УСАДЬБА ДИВНОМОРСКОЕ РЕБУС красное сухое урожай 2019 13,5%',
      wordCount: 9,
      meanConfidence: 81.4,
      error: null,
      fields: [
        { field: 'name', weight: 0.3, candidates: [{ value: 'Ребус, выдержанное красное', score: 0.64 }, { value: 'Семейный резерв', score: 0.12 }] },
        { field: 'winery', weight: 0.2, candidates: [{ value: 'Усадьба Дивноморское', score: 0.91 }] },
        { field: 'year', weight: 0.08, candidates: [{ value: '2019', score: 0.88 }] },
        { field: 'grape_varieties', weight: 0.12, candidates: [] },
        { field: 'abv', weight: null, candidates: [{ value: '13.5', score: 0.79 }] },
        { field: 'category', weight: 0.03, candidates: [{ value: 'Вино', score: 1 }] },
        { field: 'sweetness', weight: null, candidates: [{ value: 'сухое', score: 1 }] },
        { field: 'region', weight: 0.04, candidates: [] },
      ],
    },
    retriever: {
      durationMs: 1180,
      error: null,
      candidates: wines.map((wine, index) => ({
        slug: wine.slug,
        score: index === 0 ? 0.563 : 0.401 - index * 0.05,
        goodMatches: index === 0 ? 24 : 9,
        inliers: index === 0 ? 14 : 3,
        wine,
      })),
    },
    verification: {
      labelCategory: null,
      labelYear: '2019',
      labelSweetness: 'сухое',
      shortlist: [first, second].filter((wine): wine is WineCard => Boolean(wine)).map((wine, index) => ({
        slug: wine.slug,
        wine,
        readWords: index === 0 ? ['Ребус'] : [],
        contradiction: null,
        reason: null,
      })),
    },
    ranking: {
      durationMs: 4,
      status,
      score: topScore,
      margin: Math.round((topScore - secondScore) * 1000) / 1000,
      minMargin: 0.03,
      candidates: [first, second].filter((wine): wine is WineCard => Boolean(wine)).map((wine, index) => ({
        slug: wine.slug,
        score: index === 0 ? topScore : secondScore,
        wine,
        rejection: null,
        fields: index === 0
          ? [
              { field: 'name', weight: 0.3, score: status === 'matched' ? 0.64 : 0.2 },
              { field: 'winery', weight: 0.2, score: status === 'matched' ? 0.91 : 0.5 },
              { field: 'slug', weight: 0.2, score: 0.563 },
              { field: 'year', weight: 0.08, score: 0.88 },
            ]
          : [
              { field: 'name', weight: 0.3, score: 0.12 },
              { field: 'winery', weight: 0.2, score: 0 },
              { field: 'slug', weight: 0.2, score: 0.351 },
              { field: 'year', weight: 0.08, score: 0 },
            ],
      })),
    },
  }
}
