import type { SommelierBlockReason, SommelierResponse, WineCard } from '#shared/contracts'
import { checkProfanity, normalizeUnicode } from 'glin-profanity'

const russianProfanityPattern = /(?:^|[^\p{L}\p{N}])(?:бл(?:я|е)[дт]\p{L}*|[хx][уy][йея]\p{L}*|п(?:и|е)зд\p{L}*|[её]б\p{L}*|сук(?:а|и|у|ой)\p{L}*)(?=$|[^\p{L}\p{N}])/iu

export function containsProfanity(text: string): boolean {
  const normalized = text.normalize('NFKC').toLocaleLowerCase('ru-RU')
  const libraryResult = checkProfanity(normalizeUnicode(normalized), {
    languages: ['russian', 'english'],
    detectLeetspeak: true,
    leetspeakLevel: 'aggressive',
    normalizeUnicode: true,
  })

  return libraryResult.containsProfanity || russianProfanityPattern.test(normalized)
}

export function groundRecommendations(
  requestedSlugs: readonly string[],
  catalogWines: readonly WineCard[],
): WineCard[] | null {
  const winesBySlug = new Map(catalogWines.map(wine => [wine.slug, wine]))
  const uniqueSlugs = [...new Set(requestedSlugs)]

  if (uniqueSlugs.some(slug => !winesBySlug.has(slug))) {
    return null
  }

  return uniqueSlugs.flatMap((slug) => {
    const wine = winesBySlug.get(slug)
    return wine ? [wine] : []
  })
}

export function createSocialSommelierResponse(
  content: string,
  provider: SommelierResponse['provider'],
  isMock: boolean,
): SommelierResponse | null {
  const normalized = content
    .normalize('NFKC')
    .toLocaleLowerCase('ru-RU')
    .replaceAll(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
    .replaceAll(/\s+/g, ' ')
  const isGreeting = /^(?:(?:привет|приветствую|здравствуй|здравствуйте|доброе утро|добрый день|добрый вечер|хай|хеллоу|hello)(?: сомелье)?)$/u.test(normalized)
  const isGratitude = /^(?:спасибо(?: тебе| большое)?|благодарю|(?:ты )?(?:крутой|крутая|молодец)(?: спасибо)?|спасибо (?:ты )?(?:крутой|крутая|молодец))$/u.test(normalized)
  const isAcknowledgement = /^(?:ладно|ок|окей|хорошо|понятно|ясно|договорились|принято|понял|поняла)$/u.test(normalized)
  if (!isGreeting && !isGratitude && !isAcknowledgement) return null

  return {
    status: 'answered',
    message: isGreeting
      ? 'Здравствуйте! Расскажите, что будет на столе или какое вино вам нравится.'
      : isGratitude
        ? 'Пожалуйста! Рад был помочь. Если захотите новый подбор, расскажите, что будет на столе.'
        : 'Хорошо. Если захотите продолжить подбор, расскажите о новом блюде или вкусе.',
    recommendations: [],
    blockReason: null,
    provider,
    isMock,
  }
}

export function blockedSommelierResponse(
  reason: SommelierBlockReason,
  provider: SommelierResponse['provider'],
  isMock: boolean,
): SommelierResponse {
  const message = reason === 'profanity'
    ? 'Давайте без грубых выражений. Я помогу подобрать вино к блюду, событию или вкусовым предпочтениям.'
    : reason === 'unsafe'
      ? 'Я не даю советы о влиянии алкоголя на здоровье или настроение. Могу помочь только с характеристиками вина и сочетаниями с едой.'
      : 'Я отвечаю только о винах, их стилях и сочетаниях с едой. Расскажите, что будет на столе или какой вкус вам нравится.'

  return {
    status: 'blocked',
    message,
    recommendations: [],
    blockReason: reason,
    provider,
    isMock,
  }
}
