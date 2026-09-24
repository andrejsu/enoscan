import type { AstroRecommendationResponse, WineCard } from '#shared/contracts'
import { getZodiacWineProfile } from '#shared/contracts'
import { isFeatureEnabled } from '#shared/utils/feature-flags'
import { browseCatalog } from '../../utils/catalog-admin'
import { getCatalogPool } from '../../utils/catalog-db'
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
    const pool = getCatalogPool(config.databaseUrl)
    const responses = await Promise.all(profile.catalogQueries.map(q =>
      browseCatalog(pool, { q, page: 1, imageStatus: 'indexed' }),
    ))

    const seenSlugs = new Set<string>()
    const uniqueWines: WineCard[] = []
    for (const response of responses) {
      if (!response) {
        throw new Error('Catalog has not been imported')
      }
      for (const wine of response.wines) {
        if (!seenSlugs.has(wine.slug)) {
          seenSlugs.add(wine.slug)
          uniqueWines.push(wine)
        }
      }
    }

    const wines = sampleRandomItems(uniqueWines, 3)

    return { profile, wines }
  }
  catch (error) {
    throw createError({
      statusCode: 502,
      message: 'Не удалось подобрать вина. Проверьте PostgreSQL.',
      cause: error,
    })
  }
})
