import type { ScanDebug, ScanDebugField, ScanDebugOcr, ScanDebugRankingTerm } from '#shared/contracts'

export const scanDebugFieldLabels: Readonly<Record<ScanDebugField, string>> = {
  name: 'Название',
  winery: 'Винодельня',
  year: 'Год',
  grape_varieties: 'Сорта',
  abv: 'Крепость',
  category: 'Категория',
  color: 'Цвет',
  region: 'Регион',
  slug: 'Визуал',
}

export interface ScanDebugStage {
  key: keyof ScanDebug
  title: string
  durationMs: number
  summary: string
  hasProblem: boolean
}

// Raw similarity, never a percentage — see CODE_RULES «TypeScript и данные».
export function formatScore(score: number): string {
  return score.toFixed(3)
}

export function clampShare(value: number): number {
  return Math.min(1, Math.max(0, value))
}

export function cropBoxStyle(box: readonly [number, number, number, number]): Record<string, string> {
  const [left, top, right, bottom] = [clampShare(box[0]), clampShare(box[1]), clampShare(box[2]), clampShare(box[3])]
  const percent = (share: number) => `${Math.round(share * 1000) / 10}%`
  return {
    left: percent(left),
    top: percent(top),
    width: percent(Math.max(0, right - left)),
    height: percent(Math.max(0, bottom - top)),
  }
}

export interface RankingSegment {
  field: ScanDebugField
  /** weight × score / Σweight: this field's share of the wine's total score. */
  contribution: number
}

/** Splits a wine's ranking score into per-field parts that add up to the score itself. */
export function rankingSegments(terms: readonly ScanDebugRankingTerm[]): RankingSegment[] {
  const totalWeight = terms.reduce((sum, term) => sum + term.weight, 0)
  if (totalWeight <= 0) {
    return []
  }
  return terms
    .map(term => ({ field: term.field, contribution: term.weight * term.score / totalWeight }))
    .filter(segment => segment.contribution > 0)
}

export function firstFieldWithCandidates(fields: ScanDebugOcr['fields']): ScanDebugField | null {
  return fields.find(field => field.candidates.length > 0)?.field ?? fields[0]?.field ?? null
}

export function scanDebugStages(debug: ScanDebug): ScanDebugStage[] {
  const { preprocessing, ocr, retriever, ranking } = debug
  const topVisual = retriever.candidates[0]
  const filledFields = ocr.fields.filter(field => field.candidates.length > 0).length

  return [
    {
      key: 'preprocessing',
      title: 'Предобработка',
      durationMs: preprocessing.durationMs,
      summary: preprocessing.usedSam ? 'SAM-сегментация' : 'Быстрый кроп',
      hasProblem: preprocessing.warnings.some(warning => warning !== 'sam_skipped'),
    },
    {
      key: 'ocr',
      title: 'OCR',
      durationMs: ocr.durationMs,
      summary: ocr.error ? `Ошибка: ${ocr.error}` : `${ocr.wordCount} слов · ${filledFields} полей`,
      hasProblem: Boolean(ocr.error) || filledFields === 0,
    },
    {
      key: 'retriever',
      title: 'Ретривер',
      durationMs: retriever.durationMs,
      summary: retriever.error
        ? `Недоступен: ${retriever.error}`
        : topVisual ? `top-1 ${formatScore(topVisual.score)}` : 'Нет кандидатов',
      hasProblem: Boolean(retriever.error) || !topVisual,
    },
    {
      key: 'ranking',
      title: 'Ранжирование',
      durationMs: ranking.durationMs,
      summary: `${formatScore(ranking.score)} ${ranking.score > ranking.threshold ? '>' : '≤'} ${formatScore(ranking.threshold)}`,
      hasProblem: ranking.status !== 'matched',
    },
  ]
}
