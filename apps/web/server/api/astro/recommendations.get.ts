import type { AstroRecommendationResponse, CatalogAdminResponse, WineCard } from '#shared/contracts'
import { getZodiacWineProfile } from '#shared/contracts'
import { isFeatureEnabled } from '#shared/utils/feature-flags'
import { sampleRandomItems } from '../../utils/sample-random-items'

export default defineEventHandler(async (event): Promise<AstroRecommendationResponse> => {
  const config = useRuntimeConfig()

  if (!isFeatureEnabled(config.public.astroEnabled)) {
    throw createError({ statusCode: 404, message: 'Страница не найдена.' })
  }

  setResponseHeader(event, 'Cache-Control', 'no-store')

  const query = getQuery(event)
  const sign = typeof query.sign === 'string' ? query.sign : ''
  const profile = getZodiacWineProfile(sign)

  if (!profile) {
    throw createError({ statusCode: 400, message: 'Выберите один из двенадцати знаков зодиака.' })
  }

  try {
    const responses = await Promise.all(profile.catalogQueries.map(q =>
      $fetch<CatalogAdminResponse>(`${config.retrievalBaseUrl}/v1/catalog`, {
        query: { q, page: 1, per_page: 60, image_status: 'indexed' },
      }),
    ))

    const uniqueWines = new Map<string, WineCard>()
    for (const response of responses) {
      for (const wine of response.wines) {
        if (!uniqueWines.has(wine.slug)) {
          uniqueWines.set(wine.slug, wine)
        }
      }
    }

    const wines = sampleRandomItems([...uniqueWines.values()], 3)

    return { profile, wines }
  }
  catch (error) {
    throw createError({
      statusCode: 502,
      message: 'Не удалось подобрать вина. Проверьте retrieval-сервис.',
      cause: error,
    })
  }
})
