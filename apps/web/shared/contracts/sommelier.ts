import { z } from 'zod'

import type { WineCard } from './index'

export const sommelierProviderIds = ['openai', 'anthropic', 'google'] as const
export type SommelierProviderId = (typeof sommelierProviderIds)[number]

export const sommelierMessageSchema = z.object({
  role: z.enum(['user', 'assistant']),
  content: z.string().trim().min(1).max(800),
}).strict()

export const sommelierRequestSchema = z.object({
  sessionId: z.string().uuid(),
  messages: z.array(sommelierMessageSchema).min(1).max(12),
}).strict().refine(
  request => request.messages[0]?.role === 'user'
    && request.messages.at(-1)?.role === 'user'
    && request.messages.every((message, index, messages) => (
      index === 0 || message.role !== messages[index - 1]?.role
    )),
  { message: 'Сообщения должны чередоваться и начинаться с пользователя.', path: ['messages'] },
)

export const catalogSearchFiltersSchema = z.object({
  color: z.string().trim().min(1).max(80).optional(),
  region: z.string().trim().min(1).max(80).optional(),
  grapeVariety: z.string().trim().min(1).max(80).optional(),
  category: z.enum(['Белое', 'Красное', 'Розовое', 'Оранжевое']).optional(),
  occasionKeywords: z.array(z.string().trim().min(1).max(60)).max(5).optional(),
  limit: z.number().int().min(1).max(8).default(5),
}).strict()

export type SommelierMessageInput = z.infer<typeof sommelierMessageSchema>
export type SommelierRequest = z.infer<typeof sommelierRequestSchema>
export type CatalogSearchFilters = z.infer<typeof catalogSearchFiltersSchema>

export type SommelierBlockReason = 'off_topic' | 'profanity' | 'unsafe'

export interface SommelierResponse {
  status: 'answered' | 'blocked'
  message: string
  recommendations: readonly WineCard[]
  blockReason: SommelierBlockReason | null
  provider: SommelierProviderId | 'mock'
  isMock: boolean
}

export interface SommelierConversationMessage extends SommelierMessageInput {
  id: string
  recommendations: readonly WineCard[]
  status?: SommelierResponse['status']
}
