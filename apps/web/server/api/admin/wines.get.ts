import type { CatalogAdminResponse, CatalogImageStatus } from '#shared/contracts'

export default defineEventHandler(async (event): Promise<CatalogAdminResponse> => {
  const query = getQuery(event)
  const rawPage = typeof query.page === 'string' ? Number.parseInt(query.page, 10) : 1
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1
  const q = typeof query.q === 'string' ? query.q.trim().slice(0, 120) : ''
  const requestedStatus = typeof query.imageStatus === 'string' ? query.imageStatus : 'all'
  const imageStatus: CatalogImageStatus = requestedStatus === 'indexed' || requestedStatus === 'missing'
    ? requestedStatus
    : 'all'
  const config = useRuntimeConfig()

  try {
    return await $fetch<CatalogAdminResponse>(`${config.retrievalBaseUrl}/v1/catalog`, {
      query: {
        q,
        page,
        per_page: 24,
        image_status: imageStatus,
      },
    })
  }
  catch (error) {
    throw createError({
      statusCode: 502,
      message: 'Не удалось загрузить каталог. Проверьте retrieval-сервис.',
      cause: error,
    })
  }
})
