import type { ScanDebug, ScanDebugField, ScanDebugOcr, ScanDebugRankingTerm, ScanDebugVerification } from '#shared/contracts'

export const scanDebugFieldLabels: Readonly<Record<ScanDebugField, string>> = {
  name: 'Название',
  winery: 'Винодельня',
  year: 'Год',
  grape_varieties: 'Сорта',
  abv: 'Крепость',
  category: 'Категория',
  sweetness: 'Сахар',
  region: 'Регион',
  slug: 'Визуал',
}

export interface ScanDebugStage {
  key: keyof ScanDebug
  title: string
  /** null when the stage has no timing of its own (the label check runs inside ranking). */
  durationMs: number | null
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
  /** This field's share of the wine's total score. */
  contribution: number
}

/**
 * Splits a wine's score into per-field parts that add up to the score itself.
 * The score is Σ weight × per-field probability over a fixed total weight,
 * so scaling each field's weight × probability to the score is exact.
 */
export function rankingSegments(terms: readonly ScanDebugRankingTerm[], score: number): RankingSegment[] {
  const support = terms.reduce((sum, term) => sum + term.weight * term.score, 0)
  if (support <= 0) {
    return []
  }
  return terms
    .map(term => ({ field: term.field, contribution: score * term.weight * term.score / support }))
    .filter(segment => segment.contribution > 0)
}

export type VerificationVerdict = 'confirmed' | 'neutral' | 'rejected'

export const verificationVerdictLabels: Readonly<Record<VerificationVerdict, string>> = {
  confirmed: 'подтверждено',
  neutral: 'без возражений',
  rejected: 'отклонено',
}

/** Contradicted wines are rejected; the rest are confirmed when the label shows words of their name. */
export function verificationVerdict(row: ScanDebugVerification['shortlist'][number]): VerificationVerdict {
  if (row.contradiction) {
    return 'rejected'
  }
  return row.readWords.length ? 'confirmed' : 'neutral'
}

/** Score the top-1 wine had to reach for `matched`: runner-up plus the minimum margin. */
export function rankingMatchLine(ranking: ScanDebug['ranking']): number | null {
  const runnerUp = ranking.candidates[1]
  return runnerUp ? runnerUp.score + ranking.minMargin : null
}

export function firstFieldWithCandidates(fields: ScanDebugOcr['fields']): ScanDebugField | null {
  return fields.find(field => field.candidates.length > 0)?.field ?? fields[0]?.field ?? null
}

export function scanDebugStages(debug: ScanDebug): ScanDebugStage[] {
  const { preprocessing, ocr, retriever, verification, ranking } = debug
  const rejectedCount = verification.shortlist.filter(row => row.contradiction).length
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
      key: 'verification',
      title: 'Сверка с этикеткой',
      durationMs: null,
      summary: rejectedCount
        ? `отклонено ${rejectedCount} из ${verification.shortlist.length}`
        : `${verification.shortlist.length} без противоречий`,
      hasProblem: verification.shortlist.length > 0 && rejectedCount === verification.shortlist.length,
    },
    {
      key: 'ranking',
      title: 'Ранжирование',
      durationMs: ranking.durationMs,
      summary: `отрыв ${formatScore(ranking.margin)} ${ranking.margin >= ranking.minMargin ? '≥' : '<'} ${formatScore(ranking.minMargin)}`,
      hasProblem: ranking.status !== 'matched',
    },
  ]
}
