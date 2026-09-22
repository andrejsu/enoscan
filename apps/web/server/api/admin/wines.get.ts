import type { CatalogAdminResponse } from '#shared/contracts'

export default defineEventHandler(async (event): Promise<CatalogAdminResponse> => {
  const query = parseAdminQuery(getQuery(event))
  const config = useRuntimeConfig()

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
