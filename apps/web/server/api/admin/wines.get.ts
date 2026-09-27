import type { CatalogAdminResponse } from '#shared/contracts'
import { isFeatureEnabled } from '#shared/utils/feature-flags'

export default defineEventHandler(async (event): Promise<CatalogAdminResponse> => {
  const config = useRuntimeConfig()

  if (!isFeatureEnabled(config.public.catalogEnabled)) {
    throw createError({ statusCode: 404, message: 'Страница не найдена.' })
  }

  const query = parseAdminQuery(getQuery(event))

  let response: CatalogAdminResponse | null
  try {
    response = await browseCatalog(getCatalogPool(config.databaseUrl), query)
  }
  catch (error) {
    throw createError({
      statusCode: 502,
      message: 'Не удалось загрузить каталог. Проверьте PostgreSQL.',
      cause: error,
    })
  }

  if (!response) {
    throw createError({
      statusCode: 503,
      message: 'Каталог ещё не импортирован. Запустите importer.',
    })
  }
  return response
})
