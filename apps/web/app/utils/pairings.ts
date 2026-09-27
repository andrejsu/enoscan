import type { PairingTaste, PairingWine, SavedPairing } from '#shared/contracts'
import { pairingTastes } from '#shared/contracts'

// ponytail: stem regexes over free text; swap for catalog taste fields once the catalog has them.
const tastePatterns: Record<PairingTaste, RegExp> = {
  'Сухое': /сух/iu,
  'Полусладкое': /полуслад/iu,
  'Сладкое': /(?<!полу)слад/iu,
  'Игристое': /игрист|брют|шампан/iu,
  'Лёгкое': /л[её]гк/iu,
  'Насыщенное': /насыщ|полнотел|плотн/iu,
  'Свежее': /свеж|кислотн/iu,
  'Фруктовое': /фрукт|ягод/iu,
  'Минеральное': /минерал/iu,
  'Пряное': /прян|специ|перц/iu,
  'Бархатистое': /бархат|мягк|округл/iu,
}

const maxPairingLength = 120
const maxWineFieldLength = 200
// Only catalog previews: a crafted link must not make the saved list load an arbitrary URL.
const catalogPreviewPattern = /^\/api\/wines\/[^/?#]+\/image\?size=preview$/

/** Tastes mentioned in a sommelier reply or a catalog description, in catalog order. */
export function detectPairingTastes(...texts: ReadonlyArray<string | null | undefined>): PairingTaste[] {
  const text = texts.filter(Boolean).join(' ')
  return pairingTastes.filter(taste => tastePatterns[taste].test(text))
}

/** «Подбери вино к запечённой рыбе» → «к запечённой рыбе»; empty when the question names no pairing. */
export function extractPairingSubject(question: string): string {
  const match = question.match(/(?:^|\s)((?:к|ко|под|для|на)\s+[^?.!\n]+)/iu)
  if (!match?.[1]) return ''

  const subject = match[1].trim().slice(0, maxPairingLength)
  return subject.charAt(0).toLowerCase() + subject.slice(1)
}

/** Link to the pairing form with the wine and whatever the caller already knows about the pairing. */
export function pairingLocation(
  wine: PairingWine,
  context: { pairing?: string, tastes?: readonly PairingTaste[] } = {},
) {
  return {
    path: '/pairings/new',
    query: {
      slug: wine.slug,
      name: wine.name,
      producer: wine.producer,
      ...(wine.year ? { year: String(wine.year) } : {}),
      ...(wine.color ? { color: wine.color } : {}),
      ...(wine.region ? { region: wine.region } : {}),
      ...(wine.imagePreviewUrl ? { image: wine.imagePreviewUrl } : {}),
      ...(context.pairing ? { pairing: context.pairing } : {}),
      ...(context.tastes?.length ? { tastes: context.tastes.join(',') } : {}),
    },
  }
}

function optionalText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim().slice(0, maxWineFieldLength) : null
}

/**
 * The wine card from a pairing link (`image` holds the preview URL) or from storage.
 * Both are untrusted; v1 records carry only slug, name and producer, the rest becomes null.
 */
export function restorePairingWine(source: Record<string, unknown>): PairingWine | null {
  const slug = optionalText(source.slug)
  const name = optionalText(source.name)
  if (!slug || !name) return null

  const year = Number(source.year)
  const image = source.imagePreviewUrl ?? source.image

  return {
    slug,
    name,
    producer: optionalText(source.producer) ?? '',
    year: Number.isInteger(year) && year >= 1800 && year <= 2100 ? year : null,
    color: optionalText(source.color),
    region: optionalText(source.region),
    imagePreviewUrl: typeof image === 'string' && catalogPreviewPattern.test(image) ? image : null,
  }
}

/** Query and storage values are untrusted: keep only known tastes. */
export function parsePairingTastes(value: unknown): PairingTaste[] {
  const items = typeof value === 'string' ? value.split(',') : Array.isArray(value) ? value : []
  return pairingTastes.filter(taste => items.includes(taste))
}

/** Reads a stored pairing; v1 records (dish + softer/richer verdict) keep their dish as the pairing. */
export function restorePairing(value: unknown): SavedPairing | null {
  if (!value || typeof value !== 'object') return null

  const item = value as Record<string, unknown>
  const wine = item.wine && typeof item.wine === 'object'
    ? restorePairingWine(item.wine as Record<string, unknown>)
    : null
  if (
    typeof item.id !== 'string'
    || typeof item.savedAt !== 'string'
    || Number.isNaN(Date.parse(item.savedAt))
    || !wine
  ) {
    return null
  }

  const pairing = typeof item.pairing === 'string' ? item.pairing : typeof item.dish === 'string' ? item.dish : null
  if (pairing === null) return null

  return {
    id: item.id,
    wine,
    pairing: pairing.slice(0, maxPairingLength),
    tastes: parsePairingTastes(item.tastes),
    savedAt: item.savedAt,
  }
}
