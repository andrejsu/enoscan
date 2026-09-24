export const scanStatuses = ['matched', 'uncertain', 'not_found'] as const

export * from './sommelier'

export type ScanStatus = (typeof scanStatuses)[number]

export interface WineCard {
  slug: string
  name: string
  producer: string
  year: number | null
  category: string | null
  color: string | null
  region: string | null
  grapeVarieties: readonly string[]
  description: string | null
  servingTemperature: string | null
  imageUrl: string | null
  imagePreviewUrl: string | null
}

export interface ScanCandidate {
  slug: string
  score: number
  wine?: WineCard
}

export interface ScanConfidence {
  kind: 'similarity' | 'calibrated_probability'
  top1Score: number
  margin: number
  calibratedProbability?: number
}

export interface ScanTiming {
  totalMs: number
  stages: Readonly<Record<string, number>>
}

export interface ScanVersion {
  model: string
  catalog: string
  configuration: string
}

export interface ScanResponse {
  status: ScanStatus
  wine: WineCard | null
  candidates: readonly ScanCandidate[]
  confidence: ScanConfidence
  timing: ScanTiming
  alternatives: readonly WineCard[]
  version: ScanVersion
  guidance?: string
  /** Per-stage trace from the ranking service; absent when RANKING_DEBUG=false. */
  debug?: ScanDebug
  isMock: boolean
}

export const scanDebugFields = [
  'name', 'winery', 'year', 'grape_varieties', 'abv', 'category', 'color', 'region', 'slug',
] as const

export type ScanDebugField = (typeof scanDebugFields)[number]

export interface ScanDebugPreprocessing {
  durationMs: number
  usedSam: boolean
  warnings: readonly string[]
  /** Fast-crop box as [left, top, right, bottom] fractions of the source frame; null after SAM. */
  cropBox: readonly [number, number, number, number] | null
  /** JPEG data URLs: uploaded frame, color branch for visual search, what OCR read (the full frame). */
  images: { source: string, visual: string, ocr: string }
  metrics: {
    labelWidth: number | null
    labelHeight: number | null
    sharpness: number | null
    noiseSigma: number | null
    glareFraction: number | null
    isDenoised: boolean
  }
}

export interface ScanDebugFieldCandidate {
  value: string
  score: number
}

export interface ScanDebugOcr {
  durationMs: number
  passes: readonly ('crop' | 'full')[]
  text: string
  wordCount: number
  meanConfidence: number | null
  error: string | null
  fields: readonly {
    field: ScanDebugField
    /** Ranking weight; null for fields ranking does not use (abv). */
    weight: number | null
    candidates: readonly ScanDebugFieldCandidate[]
  }[]
}

export interface ScanDebugRetriever {
  durationMs: number
  error: string | null
  candidates: readonly {
    slug: string
    score: number
    goodMatches: number | null
    inliers: number | null
    wine: WineCard | null
  }[]
}

export interface ScanDebugRankingTerm {
  field: ScanDebugField
  weight: number
  score: number
}

export interface ScanDebugRanking {
  durationMs: number
  status: ScanStatus
  score: number
  threshold: number
  candidates: readonly {
    slug: string
    score: number
    wine: WineCard
    fields: readonly ScanDebugRankingTerm[]
  }[]
}

export interface ScanDebug {
  preprocessing: ScanDebugPreprocessing
  ocr: ScanDebugOcr
  retriever: ScanDebugRetriever
  ranking: ScanDebugRanking
}

export interface SavedPairing {
  id: string
  wine: Pick<WineCard, 'slug' | 'name' | 'producer'>
  dish: string
  preference: 'softer' | 'richer'
  verdict: string
  savedAt: string
}

export const catalogImageStatuses = [
  'all',
  'with_image',
  'without_image',
  'suspicious',
  'indexed',
  'not_indexed',
] as const

export type CatalogImageStatus = (typeof catalogImageStatuses)[number]

export type CatalogMappingKind = 'image_filename' | 'slug' | 'fuzzy_filename' | 'manual'

export type CatalogReviewStatus = 'auto' | 'suspicious' | 'confirmed'

export interface CatalogSummary {
  datasetVersion: string
  importedAt: string
  rawRecords: number
  uniqueWines: number
  inactiveWines: number
  duplicateSlugs: number
  images: number
  orphanImages: number
  winesWithImage: number
  suspiciousMappings: number
  indexedWines: number
}

export interface CatalogAdminWine extends WineCard {
  sourceImageFilename: string | null
  imageStrapiPath: string | null
  mappingKind: CatalogMappingKind | null
  mappingScore: number | null
  reviewStatus: CatalogReviewStatus | null
  rawRecordCount: number
  isIndexed: boolean
}

export interface CatalogPagination {
  page: number
  perPage: number
  totalItems: number
  totalPages: number
}

export interface CatalogAdminResponse {
  summary: CatalogSummary
  wines: readonly CatalogAdminWine[]
  pagination: CatalogPagination
}

export const zodiacSignIds = [
  'aries', 'taurus', 'gemini', 'cancer', 'leo', 'virgo',
  'libra', 'scorpio', 'sagittarius', 'capricorn', 'aquarius', 'pisces',
] as const

export type ZodiacSignId = (typeof zodiacSignIds)[number]

export interface ZodiacWineProfile {
  id: ZodiacSignId
  name: string
  symbol: string
  dates: string
  element: 'Огонь' | 'Земля' | 'Воздух' | 'Вода'
  tagline: string
  description: string
  wineStyles: readonly string[]
  catalogQueries: readonly string[]
  matchTerms: readonly string[]
}

export interface ZodiacWineMatch {
  profile: ZodiacWineProfile
  reasons: readonly string[]
}

export interface AstroRecommendationResponse {
  profile: ZodiacWineProfile
  wines: readonly WineCard[]
}

export const zodiacWineProfiles = [
  { id: 'aries', name: 'Овен', symbol: '♈', dates: '21 марта — 19 апреля', element: 'Огонь', tagline: 'Насыщенное и пряное', description: 'Полнотелое красное с плотными танинами, нотами чёрных ягод, перца и продолжительным послевкусием.', wineStyles: ['Сира / Шираз', 'Каберне Совиньон', 'Барбера'], catalogQueries: ['Сира', 'Шираз', 'Каберне Совиньон'], matchTerms: ['сира', 'шираз', 'каберне совиньон', 'прян', 'перец', 'насыщенн'] },
  { id: 'taurus', name: 'Телец', symbol: '♉', dates: '20 апреля — 20 мая', element: 'Земля', tagline: 'Округлое и бархатистое', description: 'Красное вино с мягкими танинами, спелой фруктовостью и объёмной текстурой без излишней резкости.', wineStyles: ['Мурведр', 'Гренаш', 'Пино Нуар'], catalogQueries: ['Мурведр', 'Гренаш', 'Пино Нуар'], matchTerms: ['мурведр', 'гренаш', 'пино нуар', 'бархат', 'мягк', 'округл'] },
  { id: 'gemini', name: 'Близнецы', symbol: '♊', dates: '21 мая — 20 июня', element: 'Воздух', tagline: 'Свежее и ароматное', description: 'Вино с высокой кислотностью, цитрусовыми и травяными оттенками; лёгкое тело делает его уместным как аперитив.', wineStyles: ['Рислинг', 'Совиньон Блан', 'Игристое'], catalogQueries: ['Рислинг', 'Совиньон Блан', 'Игристое'], matchTerms: ['рислинг', 'совиньон блан', 'игрист', 'ароматн', 'свеж', 'цитрус'] },
  { id: 'cancer', name: 'Рак', symbol: '♋', dates: '21 июня — 22 июля', element: 'Вода', tagline: 'Мягкое и сбалансированное', description: 'Округлое вино с умеренной кислотностью, деликатными танинами и оттенками спелых фруктов или сливок.', wineStyles: ['Мерло', 'Каберне Фран', 'Шардоне'], catalogQueries: ['Мерло', 'Каберне Фран', 'Шардоне'], matchTerms: ['мерло', 'каберне фран', 'шардоне', 'мягк', 'нежн', 'сливоч'] },
  { id: 'leo', name: 'Лев', symbol: '♌', dates: '23 июля — 22 августа', element: 'Огонь', tagline: 'Полнотелое и выдержанное', description: 'Концентрированное красное с выраженными танинами, дубовыми оттенками и долгим, согревающим послевкусием.', wineStyles: ['Шираз', 'Каберне Совиньон', 'Выдержанное красное'], catalogQueries: ['Шираз', 'Каберне Совиньон', 'Выдержанное'], matchTerms: ['шираз', 'каберне совиньон', 'выдержан', 'полнотел', 'насыщенн', 'долг'] },
  { id: 'virgo', name: 'Дева', symbol: '♍', dates: '23 августа — 22 сентября', element: 'Земля', tagline: 'Сухое и минеральное', description: 'Точное вино с выраженной кислотностью, сдержанной фруктовостью и минеральным послевкусием, подходящее к еде.', wineStyles: ['Совиньон Блан', 'Пино Нуар', 'Сухое белое'], catalogQueries: ['Совиньон Блан', 'Пино Нуар', 'Белое сухое'], matchTerms: ['совиньон блан', 'пино нуар', 'сухое', 'минерал', 'свеж', 'кислот'] },
  { id: 'libra', name: 'Весы', symbol: '♎', dates: '23 сентября — 22 октября', element: 'Воздух', tagline: 'Лёгкое и гармоничное', description: 'Сбалансированное вино со свежей кислотностью, чистым фруктовым ароматом и лёгким, аккуратным послевкусием.', wineStyles: ['Сухое розе', 'Рислинг', 'Игристое'], catalogQueries: ['Розовое', 'Рислинг', 'Игристое'], matchTerms: ['розов', 'рислинг', 'игрист', 'сбаланс', 'элегант', 'гармонич'] },
  { id: 'scorpio', name: 'Скорпион', symbol: '♏', dates: '23 октября — 21 ноября', element: 'Вода', tagline: 'Глубокое и структурное', description: 'Плотное красное с заметными танинами и ароматами тёмных ягод, кожи, табака или дыма, которые раскрываются постепенно.', wineStyles: ['Мальбек', 'Темпранильо', 'Неббиоло'], catalogQueries: ['Мальбек', 'Темпранильо', 'Неббиоло'], matchTerms: ['мальбек', 'темпранильо', 'неббиоло', 'дым', 'темн', 'сложн'] },
  { id: 'sagittarius', name: 'Стрелец', symbol: '♐', dates: '22 ноября — 21 декабря', element: 'Огонь', tagline: 'Яркое и пряное', description: 'Сочное красное с живой кислотностью, оттенками красных ягод, сушёных трав и специй, характерных для тёплых регионов.', wineStyles: ['Гренаш', 'Санджовезе', 'Каберне Фран'], catalogQueries: ['Гренаш', 'Санджовезе', 'Каберне Фран'], matchTerms: ['гренаш', 'санджовезе', 'каберне фран', 'прян', 'ярк', 'автохтон'] },
  { id: 'capricorn', name: 'Козерог', symbol: '♑', dates: '22 декабря — 19 января', element: 'Земля', tagline: 'Строгое и выдержанное', description: 'Структурное красное с высоким уровнем танинов, сдержанным фруктом и потенциалом развиваться при выдержке.', wineStyles: ['Бордоский бленд', 'Альянико', 'Резерв'], catalogQueries: ['Каберне Мерло', 'Резерв', 'Выдержанное'], matchTerms: ['каберне', 'мерло', 'резерв', 'выдержан', 'структур', 'танин'] },
  { id: 'aquarius', name: 'Водолей', symbol: '♒', dates: '20 января — 18 февраля', element: 'Воздух', tagline: 'Самобытное и нетипичное', description: 'Вино из редкого сорта или с необычным методом производства: мацерацией белого винограда либо естественным брожением в бутылке.', wineStyles: ['Оранжевое', 'Петнат', 'Редкий сорт'], catalogQueries: ['Оранжевое', 'Петнат', 'Вионье'], matchTerms: ['оранжев', 'петнат', 'вионье', 'натуральн', 'необыч', 'редк'] },
  { id: 'pisces', name: 'Рыбы', symbol: '♓', dates: '19 февраля — 20 марта', element: 'Вода', tagline: 'Ароматное и мягкое', description: 'Белое вино с цветочными и косточково-фруктовыми ароматами, умеренной кислотностью и округлой текстурой.', wineStyles: ['Рислинг', 'Вионье', 'Шардоне'], catalogQueries: ['Рислинг', 'Вионье', 'Шардоне'], matchTerms: ['рислинг', 'вионье', 'шардоне', 'цветоч', 'ароматн', 'мягк'] },
] as const satisfies readonly [ZodiacWineProfile, ...ZodiacWineProfile[]]

export function getZodiacWineProfile(id: string): ZodiacWineProfile | undefined {
  return zodiacWineProfiles.find(profile => profile.id === id)
}

function getStableProfile(slug: string): ZodiacWineProfile {
  let hash = 0
  for (const character of slug) {
    hash = (hash * 31 + (character.codePointAt(0) ?? 0)) >>> 0
  }

  return zodiacWineProfiles[hash % zodiacWineProfiles.length] ?? zodiacWineProfiles[0]
}

export function matchWineToZodiac(wine: WineCard): ZodiacWineMatch {
  const searchable = [
    wine.name,
    wine.category,
    wine.color,
    wine.region,
    wine.description,
    ...wine.grapeVarieties,
  ].filter((value): value is string => Boolean(value)).join(' ').toLocaleLowerCase('ru-RU')

  let bestProfile: ZodiacWineProfile = getStableProfile(wine.slug)
  let bestTerms: string[] = []

  for (const profile of zodiacWineProfiles) {
    const terms = profile.matchTerms.filter(term => searchable.includes(term))
    if (terms.length > bestTerms.length) {
      bestProfile = profile
      bestTerms = terms
    }
  }

  const reasons = bestTerms.slice(0, 2)
  return {
    profile: bestProfile,
    reasons: reasons.length ? reasons : bestProfile.wineStyles.slice(0, 2),
  }
}

export function matchScanWineToZodiac(
  scan: Pick<ScanResponse, 'status' | 'wine'>,
): ZodiacWineMatch | null {
  return scan.status === 'matched' && scan.wine
    ? matchWineToZodiac(scan.wine)
    : null
}
