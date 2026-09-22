import { createHash } from 'node:crypto'

import type { SommelierBlockReason, SommelierResponse } from '#shared/contracts'
import { sommelierRequestSchema } from '#shared/contracts'

import { classifySommelierInput, classifySommelierOutput, generateSommelierAnswer } from '../../utils/sommelier-ai'
import {
  blockedSommelierResponse,
  containsProfanity,
  createSocialSommelierResponse,
} from '../../utils/sommelier-guardrails'
import { createMockSommelierResponse } from '../../utils/sommelier-mock'
import {
  createSommelierModel,
  isSommelierProviderId,
  SommelierConfigurationError,
} from '../../utils/sommelier-provider'
import { consumeSommelierRequest } from '../../utils/sommelier-rate-limit'

function logBlocked(reason: SommelierBlockReason, sessionId: string, content: string) {
  console.warn(JSON.stringify({
    event: 'sommelier_blocked',
    reason,
    session: createHash('sha256').update(sessionId).digest('hex').slice(0, 12),
    contentHash: createHash('sha256').update(content).digest('hex').slice(0, 12),
  }))
}

export default defineEventHandler(async (event): Promise<SommelierResponse> => {
  const config = useRuntimeConfig()
  const mode = config.public.sommelierMode
  if (mode === 'off') {
    throw createError({ statusCode: 404, message: 'Страница не найдена.' })
  }
  if (mode !== 'mock' && mode !== 'live') {
    throw createError({ statusCode: 503, message: 'Некорректный режим цифрового сомелье.' })
  }

  setResponseHeader(event, 'Cache-Control', 'no-store')
  const parsed = sommelierRequestSchema.safeParse(await readBody(event))
  if (!parsed.success) {
    throw createError({ statusCode: 400, message: parsed.error.issues[0]?.message || 'Некорректный запрос.' })
  }

  const { messages, sessionId } = parsed.data
  const latestMessage = messages.at(-1)?.content || ''
  const maxRequests = Number.isSafeInteger(config.sommelierMaxRequests) && config.sommelierMaxRequests > 0
    ? config.sommelierMaxRequests
    : 20
  if (!consumeSommelierRequest(sessionId, maxRequests)) {
    throw createError({ statusCode: 429, message: 'Лимит сообщений исчерпан. Попробуйте снова через несколько минут.' })
  }

  const isMock = mode === 'mock'
  let providerId: SommelierResponse['provider'] = 'mock'
  if (!isMock) {
    if (!isSommelierProviderId(config.sommelierProvider)) {
      throw createError({ statusCode: 503, message: 'Неизвестный AI-провайдер цифрового сомелье.' })
    }
    providerId = config.sommelierProvider
  }

  if (containsProfanity(latestMessage)) {
    logBlocked('profanity', sessionId, latestMessage)
    return blockedSommelierResponse('profanity', providerId, isMock)
  }

  const socialResponse = createSocialSommelierResponse(latestMessage, providerId, isMock)
  if (socialResponse) return socialResponse

  if (isMock) {
    const response = createMockSommelierResponse(messages)
    if (response.blockReason) logBlocked(response.blockReason, sessionId, latestMessage)
    return response
  }

  try {
    const provider = createSommelierModel({
      provider: config.sommelierProvider,
      model: config.sommelierModel,
      apiKey: config.sommelierApiKey,
    })
    const inputVerdict = await classifySommelierInput(provider.model, messages)
    if (!inputVerdict.allowed) {
      const reason = inputVerdict.reason === 'unsafe' ? 'unsafe' : 'off_topic'
      logBlocked(reason, sessionId, latestMessage)
      return blockedSommelierResponse(reason, provider.id, false)
    }

    const answer = await generateSommelierAnswer(provider.model, messages, config.databaseUrl)
    if (!answer || containsProfanity(answer.message)) {
      logBlocked('unsafe', sessionId, latestMessage)
      return blockedSommelierResponse('unsafe', provider.id, false)
    }

    const outputVerdict = await classifySommelierOutput(provider.model, answer.message, answer.recommendations)
    if (!outputVerdict.allowed) {
      const reason = outputVerdict.reason === 'unsafe' ? 'unsafe' : 'off_topic'
      logBlocked(reason, sessionId, latestMessage)
      return blockedSommelierResponse(reason, provider.id, false)
    }

    return {
      status: 'answered',
      message: answer.message,
      recommendations: answer.recommendations,
      blockReason: null,
      provider: provider.id,
      isMock: false,
    }
  }
  catch (error) {
    console.error(JSON.stringify({
      event: 'sommelier_failed',
      provider: config.sommelierProvider,
      error: error instanceof Error ? error.name : 'UnknownError',
    }))
    const isConfigurationError = error instanceof SommelierConfigurationError
    throw createError({
      statusCode: isConfigurationError ? 503 : 502,
      message: isConfigurationError
        ? 'Live-режим сомелье не настроен. Проверьте провайдера, модель и API-ключ.'
        : 'Сомелье временно недоступен. Попробуйте ещё раз.',
    })
  }
})
