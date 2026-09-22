import type { StoredObject } from '../../../utils/catalog-storage'
import type { PrimaryImage } from '../../../utils/wine-images'

export default defineEventHandler(async (event) => {
  const slug = getRouterParam(event, 'slug')
  if (!slug || slug.length > 200) {
    throw createError({ statusCode: 400, message: 'Не указан slug вина.' })
  }

  const size = parseImageSize(getQuery(event).size)
  if (!size) {
    throw createError({ statusCode: 400, message: 'Размер изображения: preview или original.' })
  }

  const config = useRuntimeConfig()
  let image: PrimaryImage | null
  let stored: StoredObject | null
  try {
    image = await findPrimaryImage(getCatalogPool(config.databaseUrl), slug)
    if (!image) {
      throw createError({ statusCode: 404, message: 'Изображение вина не найдено.' })
    }

    const etag = imageEtag(image, size)
    setResponseHeaders(event, {
      'ETag': etag,
      'Cache-Control': 'public, max-age=86400',
    })
    if (getRequestHeader(event, 'if-none-match') === etag) {
      return sendNoContent(event, 304)
    }

    stored = await getImageObject(config.storage, size === 'preview' ? image.previewKey : image.objectKey)
  }
  catch (error) {
    if (isError(error)) throw error
    throw createError({
      statusCode: 502,
      message: 'Не удалось загрузить изображение вина.',
      cause: error,
    })
  }

  if (!stored) {
    console.warn(`Image object for ${slug} (${size}) is missing in storage.`)
    throw createError({ statusCode: 404, message: 'Изображение вина не найдено.' })
  }

  setResponseHeader(event, 'Content-Type', size === 'preview' ? 'image/webp' : image.mime)
  if (stored.contentLength !== undefined) {
    setResponseHeader(event, 'Content-Length', stored.contentLength)
  }
  return sendStream(event, stored.body)
})
