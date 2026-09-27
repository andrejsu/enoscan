import { createHash } from 'node:crypto'

import type { TourRouteResponse } from '#shared/contracts'
import { tourRouteRequestSchema } from '#shared/contracts'

import { containsProfanity } from '../../utils/sommelier-guardrails'
import {
  createSommelierModel,
  isSommelierProviderId,
  SommelierConfigurationError,
} from '../../utils/sommelier-provider'
import { consumeSommelierRequest } from '../../utils/sommelier-rate-limit'
import { classifyTourRouteInput, generateTourRoute, resolveTourRouteDraft } from '../../utils/tour-route-ai'
import { createMockTourRouteResponse } from '../../utils/tour-route-mock'

function blockedResponse(
  reason: 'profanity' | 'unsafe' | 'off_topic',
  provider: TourRouteResponse['provider'],
  isMock: boolean,
): TourRouteResponse {
  return {
    status: 'blocked',
    message: reason === 'profanity'
      ? 'Давайте без грубых выражений. Опишите желаемую поездку, и я соберу маршрут по винодельням.'
      : reason === 'unsafe'
        ? 'Я не даю советов о влиянии алкоголя на здоровье. Могу помочь только спланировать посещение виноделен.'
        : 'Я строю только маршруты по винодельням. Укажите регион, длительность, бюджет или желаемый формат.',
    route: null,
    provider,
    isMock,
  }
}

export default defineEventHandler(async (event): Promise<TourRouteResponse> => {
  const config = useRuntimeConfig()
  const mode = config.public.sommelierMode
  if (mode === 'off') {
    throw createError({ statusCode: 404, message: 'Маршрутный ассистент отключён.' })
  }
  if (mode !== 'mock' && mode !== 'live') {
    throw createError({ statusCode: 503, message: 'Некорректный режим маршрутного ассистента.' })
  }

  setResponseHeader(event, 'Cache-Control', 'no-store')
  const parsed = tourRouteRequestSchema.safeParse(await readBody(event))
  if (!parsed.success) {
    throw createError({ statusCode: 400, message: parsed.error.issues[0]?.message || 'Некорректный запрос.' })
  }

  const { messages, sessionId } = parsed.data
  const latestMessage = messages.at(-1)?.content || ''
  let providerId: TourRouteResponse['provider'] = 'mock'
  if (mode === 'live') {
    if (!isSommelierProviderId(config.sommelierProvider)) {
      throw createError({ statusCode: 503, message: 'Неизвестный AI-провайдер маршрутного ассистента.' })
    }
    providerId = config.sommelierProvider
  }
  const maxRequests = Number.isSafeInteger(config.sommelierMaxRequests) && config.sommelierMaxRequests > 0
    ? config.sommelierMaxRequests
    : 20
  if (!consumeSommelierRequest(`tour:${sessionId}`, maxRequests)) {
    throw createError({ statusCode: 429, message: 'Лимит маршрутов исчерпан. Попробуйте снова через несколько минут.' })
  }

  if (containsProfanity(latestMessage)) {
    return blockedResponse('profanity', providerId, mode === 'mock')
  }

  if (mode === 'mock') {
    return createMockTourRouteResponse(messages)
  }

  try {
    const provider = createSommelierModel({
      provider: config.sommelierProvider,
      model: config.sommelierModel,
      apiKey: config.sommelierApiKey,
    })
    const verdict = await classifyTourRouteInput(provider.model, messages)
    if (!verdict.allowed) {
      return blockedResponse(verdict.reason === 'unsafe' ? 'unsafe' : 'off_topic', provider.id, false)
    }

    const draft = await generateTourRoute(provider.model, messages)
    const route = resolveTourRouteDraft(draft)
    if (!route || containsProfanity(draft.message)) {
      return blockedResponse('unsafe', provider.id, false)
    }

    return {
      status: 'planned',
      message: draft.message,
      route,
      provider: provider.id,
      isMock: false,
    }
  }
  catch (error) {
    console.error(JSON.stringify({
      event: 'tour_route_failed',
      provider: config.sommelierProvider,
      session: createHash('sha256').update(sessionId).digest('hex').slice(0, 12),
      error: error instanceof Error ? error.name : 'UnknownError',
    }))
    const isConfigurationError = error instanceof SommelierConfigurationError
    throw createError({
      statusCode: isConfigurationError ? 503 : 502,
      message: isConfigurationError
        ? 'Live-режим ассистента не настроен. Проверьте провайдера, модель и API-ключ.'
        : 'Не удалось построить маршрут. Попробуйте переформулировать запрос.',
    })
  }
})
