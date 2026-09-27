import { z } from 'zod'

import type { SommelierProviderId } from './sommelier'
import { sommelierMessageSchema } from './sommelier'

export const tourRouteRequestSchema = z.object({
  sessionId: z.string().uuid(),
  messages: z.array(sommelierMessageSchema).min(1).max(10),
}).strict().refine(
  request => request.messages[0]?.role === 'user'
    && request.messages.at(-1)?.role === 'user'
    && request.messages.every((message, index, messages) => (
      index === 0 || message.role !== messages[index - 1]?.role
    )),
  { message: 'Сообщения должны чередоваться и начинаться с пользователя.', path: ['messages'] },
)

export const tourRouteDraftSchema = z.object({
  message: z.string().trim().min(1).max(700),
  title: z.string().trim().min(1).max(100),
  summary: z.string().trim().min(1).max(320),
  tourIds: z.array(z.string().trim().min(1)).min(1).max(4),
  days: z.number().int().min(1).max(3),
}).strict()

export type TourRouteRequest = z.infer<typeof tourRouteRequestSchema>
export type TourRouteDraft = z.infer<typeof tourRouteDraftSchema>
export type TourRouteMessageInput = z.infer<typeof sommelierMessageSchema>

export interface TourRoutePlan {
  title: string
  summary: string
  tourIds: readonly string[]
  days: number
  estimatedPricePerPerson: number
}

export interface TourRouteResponse {
  status: 'planned' | 'clarification' | 'blocked'
  message: string
  route: TourRoutePlan | null
  provider: SommelierProviderId | 'mock'
  isMock: boolean
}

export interface TourRouteConversationMessage extends TourRouteMessageInput {
  id: string
  route: TourRoutePlan | null
}
