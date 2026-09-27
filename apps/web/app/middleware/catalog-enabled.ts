import { isFeatureEnabled } from '#shared/utils/feature-flags'

export default defineNuxtRouteMiddleware(() => {
  const config = useRuntimeConfig()

  if (!isFeatureEnabled(config.public.catalogEnabled)) {
    return navigateTo('/', { replace: true })
  }
})
