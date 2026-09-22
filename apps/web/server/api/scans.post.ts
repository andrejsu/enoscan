import type { ScanResponse, WineCard } from '#shared/contracts'

const MAX_FILE_SIZE = 10 * 1024 * 1024
const acceptedTypes = new Set(['application/octet-stream', 'image/jpeg', 'image/png', 'image/webp'])

const demoWine: WineCard = {
  slug: 'usadba-divnomorskoe-rebus-2019',
  name: 'Ребус, выдержанное красное',
  producer: 'Усадьба Дивноморское',
  year: 2019,
  category: 'Вино',
  color: 'Красное',
  region: 'Краснодарский край',
  grapeVarieties: ['Каберне Совиньон', 'Мерло'],
  description: 'Сухое красное вино с насыщенным вкусом и пряными оттенками.',
  servingTemperature: '16–18 °C',
  imageUrl: null,
  imagePreviewUrl: null,
}

const demoAlternative: WineCard = {
  slug: 'sikory-family-reserve-2020',
  name: 'Семейный резерв',
  producer: 'Имение Сикоры',
  year: 2020,
  category: 'Вино',
  color: 'Красное',
  region: 'Семигорье',
  grapeVarieties: ['Каберне Совиньон'],
  description: null,
  servingTemperature: '16–18 °C',
  imageUrl: null,
  imagePreviewUrl: null,
}

export default defineEventHandler(async (event): Promise<ScanResponse> => {
  const parts = await readMultipartFormData(event)
  const image = parts?.find(part => part.name === 'image' && part.data.length > 0)

  if (!image) {
    throw createError({
      statusCode: 400,
      message: 'Добавьте фотографию в поле image.',
    })
  }

  if (!image.type || !acceptedTypes.has(image.type)) {
    throw createError({
      statusCode: 415,
      message: 'Поддерживаются JPEG, PNG и WebP.',
    })
  }

  if (image.data.length > MAX_FILE_SIZE) {
    throw createError({
      statusCode: 413,
      message: 'Размер фотографии не должен превышать 10 МБ.',
    })
  }

  const config = useRuntimeConfig()
  if (config.public.scanMode !== 'mock') {
    const body = new FormData()
    body.append(
      'image',
      new Blob([new Uint8Array(image.data)], { type: image.type }),
      image.filename || 'wine-label',
    )

    try {
      return await $fetch<ScanResponse>(`${config.retrievalBaseUrl}/v1/search`, {
        method: 'POST',
        body,
        timeout: 10_000,
      })
    }
    catch (error) {
      throw createError({
        statusCode: 502,
        message: 'Сервис распознавания временно недоступен. Попробуйте ещё раз.',
        cause: error,
      })
    }
  }

  // Mock branches make every product state reproducible before the CV service exists.
  const filename = image.filename?.toLowerCase() || ''
  const status = filename.includes('uncertain')
    ? 'uncertain'
    : filename.includes('not-found')
      ? 'not_found'
      : 'matched'

  await new Promise(resolve => setTimeout(resolve, 650))

  return {
    status,
    wine: status === 'matched' ? demoWine : null,
    candidates: [
      { slug: demoWine.slug, score: 0.827, wine: demoWine },
      { slug: demoAlternative.slug, score: 0.781, wine: demoAlternative },
    ],
    confidence: {
      kind: 'similarity',
      top1Score: 0.827,
      margin: 0.046,
    },
    timing: {
      totalMs: 650,
      stages: { mock: 650 },
    },
    alternatives: status === 'not_found' ? [demoAlternative] : [],
    version: {
      model: 'mock',
      catalog: 'demo-v1',
      configuration: 'web-scaffold',
    },
    guidance: status === 'uncertain'
      ? 'Приблизьте этикетку, уберите блик и убедитесь, что год попал в кадр.'
      : status === 'not_found'
        ? 'Попробуйте другой ракурс. Похожие вина будут показаны отдельно после подключения каталога.'
        : undefined,
    isMock: true,
  }
})
