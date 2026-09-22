import type { SommelierMessageInput, SommelierResponse, WineCard } from '#shared/contracts'

import { blockedSommelierResponse } from './sommelier-guardrails'

const mockWines = {
  red: {
    slug: 'usadba-divnomorskoe-rebus-2019',
    name: 'Ребус, выдержанное красное',
    producer: 'Усадьба Дивноморское',
    year: 2019,
    category: 'Вино',
    color: 'Красное',
    region: 'Краснодарский край',
    grapeVarieties: ['Каберне Совиньон', 'Мерло'],
    description: 'Сухое красное вино с насыщенным вкусом и пряными оттенками.',
    servingTemperature: '16–18 °C',
    imageUrl: null,
  },
  white: {
    slug: 'demo-riesling-white',
    name: 'Рислинг, сухое белое',
    producer: 'Демонстрационная винодельня',
    year: null,
    category: 'Вино',
    color: 'Белое',
    region: 'Краснодарский край',
    grapeVarieties: ['Рислинг'],
    description: 'Свежее сухое вино с цитрусовыми оттенками и заметной кислотностью.',
    servingTemperature: '8–10 °C',
    imageUrl: null,
  },
  sparkling: {
    slug: 'demo-brut-sparkling',
    name: 'Брют, игристое',
    producer: 'Демонстрационная винодельня',
    year: null,
    category: 'Игристое вино',
    color: 'Белое',
    region: 'Крым',
    grapeVarieties: ['Шардоне'],
    description: 'Сухое игристое вино с лёгкими фруктовыми и хлебными оттенками.',
    servingTemperature: '6–8 °C',
    imageUrl: null,
  },
} as const satisfies Record<string, WineCard>

const wineTopicPattern = /вин|ужин|блюд|ед[ау]|мяс|рыб|сыр|паст|десерт|подар|празд|событ|сорт|виноград|регион|красн|бел|розов|игрист|сух|слад|кислот|танин|аромат|вкус|бокал|выбрать|подобр|посовет/iu
const greetingPattern = /^(привет|здравствуй|добрый (день|вечер)|что (ты )?умеешь)[.!?\s]*$/iu
const injectionPattern = /игнорируй|забудь (все|предыдущ)|system prompt|системн(ый|ые) (промпт|инструкц)|представь,? что ты|base64|режим разработчика/iu
const unsafePattern = /здоров|леч|депрес|настроен|беремен|лекарств|похмел|польз|давлен|сердц/iu

export function createMockSommelierResponse(
  messages: readonly SommelierMessageInput[],
): SommelierResponse {
  const userText = messages.filter(message => message.role === 'user').map(message => message.content).join(' ')
  const latest = messages.at(-1)?.content || ''

  if (unsafePattern.test(latest)) {
    return blockedSommelierResponse('unsafe', 'mock', true)
  }
  if (injectionPattern.test(latest) || (!wineTopicPattern.test(userText) && !greetingPattern.test(latest))) {
    return blockedSommelierResponse('off_topic', 'mock', true)
  }

  if (greetingPattern.test(latest)) {
    return {
      status: 'answered',
      message: 'Здравствуйте. Расскажите, что будет на столе, какой стиль вина вам нравится и насколько торжественным будет повод.',
      recommendations: [],
      blockReason: null,
      provider: 'mock',
      isMock: true,
    }
  }

  const recommendations = /рыб|морепродукт|салат|бел/iu.test(userText)
    ? [mockWines.white]
    : /празд|игрист|аперитив|тост/iu.test(userText)
      ? [mockWines.sparkling]
      : [mockWines.red]

  return {
    status: 'answered',
    message: recommendations[0] === mockWines.white
      ? 'К лёгкому блюду подойдёт сухой стиль с живой кислотностью: он поддержит вкус еды и не перекроет его.'
      : recommendations[0] === mockWines.sparkling
        ? 'Для праздничного повода уместен сухой игристый стиль: свежая кислотность хорошо работает как аперитив.'
        : 'К насыщенному блюду подойдёт сухое красное с заметными танинами и пряным профилем.',
    recommendations,
    blockReason: null,
    provider: 'mock',
    isMock: true,
  }
}
