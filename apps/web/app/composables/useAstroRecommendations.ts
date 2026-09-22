import type { AstroRecommendationResponse, ZodiacSignId } from '#shared/contracts'

type AstroRecommendationState
  = | { status: 'idle' }
    | { status: 'loading', sign: ZodiacSignId }
    | { status: 'success', sign: ZodiacSignId, response: AstroRecommendationResponse }
    | { status: 'error', sign: ZodiacSignId, message: string }

export function useAstroRecommendations() {
  const state = ref<AstroRecommendationState>({ status: 'idle' })

  const selectedSign = computed(() => state.value.status === 'idle' ? null : state.value.sign)
  const isLoading = computed(() => state.value.status === 'loading')
  const response = computed(() => state.value.status === 'success' ? state.value.response : null)
  const errorMessage = computed(() => state.value.status === 'error' ? state.value.message : null)

  async function selectSign(sign: ZodiacSignId) {
    if (state.value.status === 'loading') {
      return
    }

    state.value = { status: 'loading', sign }

    try {
      const recommendation = await $fetch<AstroRecommendationResponse>('/api/astro/recommendations', {
        query: { sign },
      })
      state.value = { status: 'success', sign, response: recommendation }
    }
    catch {
      state.value = {
        status: 'error',
        sign,
        message: 'Не удалось открыть каталог. Попробуйте ещё раз.',
      }
    }
  }

  function retry() {
    if (state.value.status === 'error') {
      void selectSign(state.value.sign)
    }
  }

  return {
    errorMessage,
    isLoading,
    response,
    selectedSign,
    retry,
    selectSign,
  }
}
