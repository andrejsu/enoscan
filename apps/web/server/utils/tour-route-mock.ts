import type { TourRouteMessageInput, TourRouteResponse } from '#shared/contracts'
import type { WineTour, WineTourFormat, WineTourRegion } from '#shared/tours/catalog'
import { wineTours } from '#shared/tours/catalog'

const routeTopicPattern = /тур|маршрут|поезд|выходн|винодел|виноград|дегустац|экскурс|крым|балаклав|ялт|понизов|инкерман|нов(ый|ого) свет|судак|альм|вилин|уппа|родн|севастопол|краснодар|кубан|таман|новоросс|игрист|шампан|закат|погреб|терруар|биодинам|автохтон/iu
const greetingPattern = /^(привет|здравствуй|здравствуйте|добрый (день|вечер)|что (ты )?умеешь)[.!?\s]*$/iu
const injectionPattern = /игнорируй|забудь (все|предыдущ)|system prompt|системн(ый|ые) (промпт|инструкц)|режим разработчика/iu

function extractBudget(text: string): number | null {
  const match = text.match(/(?:до|бюджет(?:ом)?|примерно)?\s*(\d[\d\s]*)\s*(тыс(?:яч[аиу]?)?|₽|руб(?:лей|ля|ль)?)/iu)
  if (!match?.[1] || !match[2]) return null

  const amount = Number.parseInt(match[1].replaceAll(/\s/g, ''), 10)
  if (!Number.isFinite(amount)) return null
  return /тыс/iu.test(match[2]) ? amount * 1000 : amount
}

function extractDays(text: string): number {
  const match = text.match(/([1-3])\s*(?:день|дня|дней)/iu)
  return match?.[1] ? Number.parseInt(match[1], 10) : 1
}

function inferRegion(text: string): WineTourRegion | null {
  if (/крым|балаклав|ялт|понизов|инкерман|нов(ый|ого) свет|судак|альм|вилин|уппа|родн|севастопол/iu.test(text)) return 'crimea'
  if (/краснодар|кубан|таман|новоросс/iu.test(text)) return 'krasnodar'
  return null
}

function inferFormat(text: string): WineTourFormat | null {
  if (/закат/iu.test(text)) return 'sunset'
  if (/без дегустац|только экскурс|архитект/iu.test(text)) return 'excursion'
  if (/дегустац|игрист|мастер-класс/iu.test(text)) return 'tasting'
  return null
}

function scoreTour(tour: WineTour, text: string, region: WineTourRegion | null, format: WineTourFormat | null) {
  let score = 0
  if (region) score += tour.region === region ? 8 : -12
  if (format) score += tour.format === format ? 6 : -2
  if (/игрист|шампан/iu.test(text) && tour.id === 'golden-balka-sparkling') score += 12
  if (/игрист|шампан/iu.test(text) && tour.id === 'new-world-wine-historical') score += 10
  if (/закат/iu.test(text) && tour.id === 'sikory-sunset') score += 12
  if (/архитект/iu.test(text) && tour.id === 'winepark-intro') score += 12
  if (/мастер-класс/iu.test(text) && tour.id === 'taman-masterclass') score += 12
  if (/погреб/iu.test(text) && tour.location === 'Балаклава') score += 5
  if (/подзем|штольн|инкерман/iu.test(text) && tour.id === 'inkerman-underground') score += 14
  if (/нов(ый|ого) свет|голиц/iu.test(text) && tour.location === 'Новый Свет') score += 12
  if (/биодинам|органик|уппа/iu.test(text) && tour.id === 'uppa-biodynamic') score += 14
  if (/альм|alma|гравитац/iu.test(text) && tour.id === 'alma-valley-standard') score += 12
  if (/автохтон/iu.test(text) && tour.id === 'winepark-autochthons') score += 14
  return score
}

function selectTours(text: string, days: number, budget: number | null): WineTour[] {
  const region = inferRegion(text)
  const format = inferFormat(text)
  const targetCount = days === 1 ? 1 : Math.min(4, days * 2)
  const ranked = [...wineTours]
    .filter(tour => !region || tour.region === region)
    .sort((first, second) => (
      scoreTour(second, text, region, format) - scoreTour(first, text, region, format)
      || first.price - second.price
    ))

  const selected: WineTour[] = []
  let estimatedPrice = 0

  for (const tour of ranked) {
    if (selected.length >= targetCount) break
    if (selected.some(item => item.location === tour.location)) continue
    if (budget && estimatedPrice + tour.price > budget) continue
    selected.push(tour)
    estimatedPrice += tour.price
  }

  for (const tour of ranked) {
    if (selected.length >= targetCount) break
    if (selected.some(item => item.id === tour.id)) continue
    if (budget && estimatedPrice + tour.price > budget) continue
    selected.push(tour)
    estimatedPrice += tour.price
  }

  if (!selected.length && ranked[0]) selected.push(ranked[0])
  return selected.sort((first, second) => (
    first.coordinates.lng - second.coordinates.lng
    || first.coordinates.lat - second.coordinates.lat
  ))
}

export function createMockTourRouteResponse(
  messages: readonly TourRouteMessageInput[],
): TourRouteResponse {
  const userText = messages.filter(message => message.role === 'user').map(message => message.content).join(' ')
  const latest = messages.at(-1)?.content || ''

  if (greetingPattern.test(latest)) {
    return {
      status: 'clarification',
      message: 'Расскажите, куда хотите поехать, на сколько дней и какой бюджет заложить на одного человека.',
      route: null,
      provider: 'mock',
      isMock: true,
    }
  }

  if (injectionPattern.test(latest) || !routeTopicPattern.test(userText)) {
    return {
      status: 'blocked',
      message: 'Я строю только маршруты по винодельням. Укажите регион, длительность поездки или любимый формат.',
      route: null,
      provider: 'mock',
      isMock: true,
    }
  }

  const days = extractDays(userText)
  const budget = extractBudget(userText)
  const selected = selectTours(userText, days, budget)
  const estimatedPricePerPerson = selected.reduce((total, tour) => total + tour.price, 0)
  const regionLabel = inferRegion(userText) === 'crimea'
    ? 'по Крыму'
    : inferRegion(userText) === 'krasnodar'
      ? 'по Краснодарскому краю'
      : 'по винному югу'
  const title = days === 1 ? `Один день ${regionLabel}` : `${days} дня ${regionLabel}`

  return {
    status: 'planned',
    message: selected.length === 1
      ? 'Отметил одну точку на карте и рассчитал стоимость на одного человека.'
      : `Собрал маршрут из ${selected.length} точек. Линия на карте показывает порядок поездки, а стоимость рассчитана на одного человека.`,
    route: {
      title,
      summary: 'Маршрут чередует знакомство с местом и дегустационные впечатления, чтобы поездка не превратилась в марафон экскурсий.',
      tourIds: selected.map(tour => tour.id),
      days,
      estimatedPricePerPerson,
    },
    provider: 'mock',
    isMock: true,
  }
}
