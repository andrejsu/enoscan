import type {
  SommelierConversationMessage,
  SommelierMessageInput,
  SommelierResponse,
  WineCard,
} from '#shared/contracts'

type SommelierChatState
  = | { status: 'idle' }
    | { status: 'submitting' }
    | { status: 'error', message: string }

const HISTORY_KEY = 'vinolog:sommelier:history:v1'
const SESSION_KEY = 'vinolog:sommelier:session:v1'

function isWineCard(value: unknown): value is WineCard {
  if (!value || typeof value !== 'object') return false
  const wine = value as Partial<WineCard>
  return typeof wine.slug === 'string'
    && typeof wine.name === 'string'
    && typeof wine.producer === 'string'
    && Array.isArray(wine.grapeVarieties)
}

function isConversationMessage(value: unknown): value is SommelierConversationMessage {
  if (!value || typeof value !== 'object') return false
  const message = value as Partial<SommelierConversationMessage>
  return typeof message.id === 'string'
    && (message.role === 'user' || message.role === 'assistant')
    && typeof message.content === 'string'
    && message.content.length <= 900
    && Array.isArray(message.recommendations)
    && message.recommendations.every(isWineCard)
}

function restoreConversation(value: unknown): SommelierConversationMessage[] {
  if (!Array.isArray(value)) return []

  const restored: SommelierConversationMessage[] = []
  for (const message of value.filter(isConversationMessage)) {
    const expectedRole = restored.length % 2 === 0 ? 'user' : 'assistant'
    if (message.role === expectedRole) restored.push(message)
  }
  return restored.slice(-20)
}

function newId() {
  return crypto.randomUUID()
}

function getErrorMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'data' in error) {
    const data = error.data
    if (data && typeof data === 'object' && 'message' in data && typeof data.message === 'string') {
      return data.message
    }
  }
  return 'Не удалось получить ответ. Проверьте соединение и попробуйте ещё раз.'
}

export function useSommelierChat() {
  const messages = ref<SommelierConversationMessage[]>([])
  const state = ref<SommelierChatState>({ status: 'idle' })
  const sessionId = ref('')
  const isHydrated = ref(false)

  const isSubmitting = computed(() => state.value.status === 'submitting')
  const errorMessage = computed(() => state.value.status === 'error' ? state.value.message : null)

  onMounted(() => {
    sessionId.value = localStorage.getItem(SESSION_KEY) || newId()
    localStorage.setItem(SESSION_KEY, sessionId.value)

    try {
      const stored = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]') as unknown
      messages.value = restoreConversation(stored)
      if (messages.value.at(-1)?.role === 'user') {
        state.value = {
          status: 'error',
          message: 'Предыдущий запрос не был завершён. Его можно отправить повторно.',
        }
      }
    }
    catch {
      localStorage.removeItem(HISTORY_KEY)
    }
    isHydrated.value = true
  })

  watch(messages, (value) => {
    if (import.meta.client && isHydrated.value) {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(value.slice(-20)))
    }
  }, { deep: true })

  async function requestAnswer() {
    state.value = { status: 'submitting' }
    const apiMessages: SommelierMessageInput[] = messages.value
      .map(({ role, content }) => ({ role, content }))
      .slice(-11)

    try {
      const response = await $fetch<SommelierResponse>('/api/sommelier/chat', {
        method: 'POST',
        body: { sessionId: sessionId.value, messages: apiMessages },
      })
      messages.value.push({
        id: newId(),
        role: 'assistant',
        content: response.message,
        recommendations: response.recommendations,
        status: response.status,
      })
      state.value = { status: 'idle' }
    }
    catch (error) {
      state.value = { status: 'error', message: getErrorMessage(error) }
    }
  }

  async function send(content: string) {
    const trimmed = content.trim()
    if (!trimmed || state.value.status === 'submitting') return

    if (state.value.status === 'error' && messages.value.at(-1)?.role === 'user') {
      messages.value.pop()
    }
    messages.value.push({ id: newId(), role: 'user', content: trimmed, recommendations: [] })
    await requestAnswer()
  }

  async function retry() {
    if (state.value.status === 'error' && messages.value.at(-1)?.role === 'user') {
      await requestAnswer()
    }
  }

  function clear() {
    messages.value = []
    state.value = { status: 'idle' }
  }

  return { clear, errorMessage, isSubmitting, messages, retry, send }
}
