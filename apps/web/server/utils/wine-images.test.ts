import { describe, expect, it } from 'vitest'

import { imageEtag, parseImageSize, wineImageUrls } from './wine-images'

describe('wine image helpers', () => {
  it('defaults to the original size and rejects unknown sizes', () => {
    expect(parseImageSize(undefined)).toBe('original')
    expect(parseImageSize('preview')).toBe('preview')
    expect(parseImageSize('original')).toBe('original')
    expect(parseImageSize('huge')).toBeNull()
    expect(parseImageSize(['preview'])).toBeNull()
  })

  it('builds escaped urls only for wines with an image', () => {
    expect(wineImageUrls('пино нуар/2020', true)).toEqual({
      imageUrl: '/api/wines/%D0%BF%D0%B8%D0%BD%D0%BE%20%D0%BD%D1%83%D0%B0%D1%80%2F2020/image',
      imagePreviewUrl: '/api/wines/%D0%BF%D0%B8%D0%BD%D0%BE%20%D0%BD%D1%83%D0%B0%D1%80%2F2020/image?size=preview',
    })
    expect(wineImageUrls('slug', false)).toEqual({ imageUrl: null, imagePreviewUrl: null })
  })

  it('uses content hash and size in the etag', () => {
    const image = { sha256: 'abc', objectKey: 'o', previewKey: 'p', mime: 'image/webp' }
    expect(imageEtag(image, 'preview')).toBe('"abc-preview"')
    expect(imageEtag(image, 'original')).not.toBe(imageEtag(image, 'preview'))
  })
})
