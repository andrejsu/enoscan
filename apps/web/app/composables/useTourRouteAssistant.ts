import type {
  TourRouteConversationMessage,
  TourRouteMessageInput,
  TourRoutePlan,
  TourRouteResponse,
} from '#shared/contracts'

type TourRouteAssistantState
  = | { status: 'idle' }
    | { status: 'submitting' }
    | { status: 'error', message: string }

const sessionKey = 'vinolog:tour-route:session:v1'

function getErrorMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'data' in error) {
    const data = error.data
    if (data && typeof data === 'object' && 'message' in data && typeof data.message === 'string') {
      return data.message
    }
  }
  return 'Не удалось построить маршрут. Проверьте соединение и попробуйте ещё раз.'
}

function newId() {
  return crypto.randomUUID()
}

export function useTourRouteAssistant() {
  const config = useRuntimeConfig()
  const messages = ref<TourRouteConversationMessage[]>([])
  const currentRoute = ref<TourRoutePlan | null>(null)
  const state = ref<TourRouteAssistantState>({ status: 'idle' })
  const sessionId = ref('')
  const isHydrated = ref(false)
  const lastResponseIsMock = ref(config.public.sommelierMode === 'mock')

  const isSubmitting = computed(() => state.value.status === 'submitting')
  const errorMessage = computed(() => state.value.status === 'error' ? state.value.message : null)

  onMounted(() => {
    sessionId.value = localStorage.getItem(sessionKey) || newId()
    localStorage.setItem(sessionKey, sessionId.value)
    isHydrated.value = true
  })

  async function requestRoute() {
    state.value = { status: 'submitting' }
    const apiMessages: TourRouteMessageInput[] = messages.value
      .map(({ role, content }) => ({ role, content }))
      .slice(-9)

    try {
      const response = await $fetch<TourRouteResponse>('/api/tours/route', {
        method: 'POST',
        body: { sessionId: sessionId.value, messages: apiMessages },
      })
      messages.value.push({
        id: newId(),
        role: 'assistant',
        content: response.message,
        route: response.route,
      })
      if (response.route) currentRoute.value = response.route
      lastResponseIsMock.value = response.isMock
      state.value = { status: 'idle' }
    }
    catch (error) {
      state.value = { status: 'error', message: getErrorMessage(error) }
    }
  }

  async function send(content: string) {
    const trimmed = content.trim()
    if (!trimmed || !isHydrated.value || state.value.status === 'submitting') return

    if (state.value.status === 'error' && messages.value.at(-1)?.role === 'user') {
      messages.value.pop()
    }
    messages.value.push({ id: newId(), role: 'user', content: trimmed, route: null })
    await requestRoute()
  }

  async function retry() {
    if (state.value.status === 'error' && messages.value.at(-1)?.role === 'user') {
      await requestRoute()
    }
  }

  function clear() {
    messages.value = []
    currentRoute.value = null
    state.value = { status: 'idle' }
  }

  return {
    clear,
    currentRoute: readonly(currentRoute),
    errorMessage,
    isHydrated: readonly(isHydrated),
    isMock: readonly(lastResponseIsMock),
    isSubmitting,
    messages: readonly(messages),
    retry,
    send,
  }
}
