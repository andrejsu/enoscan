import type { Pool } from 'pg'

export const wineImageSizes = ['original', 'preview'] as const

export type WineImageSize = (typeof wineImageSizes)[number]

export interface PrimaryImage {
  sha256: string
  objectKey: string
  previewKey: string
  mime: string
}

export function parseImageSize(value: unknown): WineImageSize | null {
  if (value === undefined) return 'original'
  return wineImageSizes.find(size => size === value) ?? null
}

export function wineImageUrls(slug: string, hasImage: boolean): { imageUrl: string | null, imagePreviewUrl: string | null } {
  if (!hasImage) return { imageUrl: null, imagePreviewUrl: null }
  const imageUrl = `/api/wines/${encodeURIComponent(slug)}/image`
  return { imageUrl, imagePreviewUrl: `${imageUrl}?size=preview` }
}

export function imageEtag(image: PrimaryImage, size: WineImageSize): string {
  return `"${image.sha256}-${size}"`
}

export async function findPrimaryImage(pool: Pool, slug: string): Promise<PrimaryImage | null> {
  const result = await pool.query<{ sha256: string, object_key: string, preview_key: string, mime: string }>(
    `
      SELECT i.sha256, i.object_key, i.preview_key, i.mime
      FROM wine_images wi
      JOIN wines w ON w.slug = wi.slug AND w.is_active
      JOIN images i ON i.sha256 = wi.image_sha256
      WHERE wi.slug = $1 AND wi.is_primary
    `,
    [slug],
  )
  const row = result.rows[0]
  if (!row) return null
  return { sha256: row.sha256, objectKey: row.object_key, previewKey: row.preview_key, mime: row.mime }
}
