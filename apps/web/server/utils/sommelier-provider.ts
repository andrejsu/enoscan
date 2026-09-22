import { createAnthropic } from '@ai-sdk/anthropic'
import { createGoogleGenerativeAI } from '@ai-sdk/google'
import { createOpenAI } from '@ai-sdk/openai'
import { sommelierProviderIds } from '#shared/contracts'
import type { SommelierProviderId } from '#shared/contracts'
import type { LanguageModel } from 'ai'

interface SommelierProviderConfig {
  provider: string
  model: string
  apiKey: string
}

const defaultModels: Record<SommelierProviderId, string> = {
  openai: 'gpt-5-mini',
  anthropic: 'claude-haiku-4-5',
  google: 'gemini-3.1-flash-lite',
}

export interface SommelierModel {
  id: SommelierProviderId
  modelId: string
  model: LanguageModel
}

export class SommelierConfigurationError extends Error {
  override name = 'SommelierConfigurationError'
}

export function isSommelierProviderId(value: string): value is SommelierProviderId {
  return sommelierProviderIds.some(provider => provider === value)
}

export function createSommelierModel(config: SommelierProviderConfig): SommelierModel {
  if (!isSommelierProviderId(config.provider)) {
    throw new SommelierConfigurationError(`Unsupported sommelier provider: ${config.provider}`)
  }
  const provider = config.provider
  const modelId = config.model || defaultModels[provider]

  if (!config.apiKey) {
    throw new SommelierConfigurationError(`API key is missing for sommelier provider: ${provider}`)
  }

  if (provider === 'openai') {
    return { id: provider, modelId, model: createOpenAI({ apiKey: config.apiKey })(modelId) }
  }
  if (provider === 'anthropic') {
    return { id: provider, modelId, model: createAnthropic({ apiKey: config.apiKey })(modelId) }
  }

  return { id: provider, modelId, model: createGoogleGenerativeAI({ apiKey: config.apiKey })(modelId) }
}
