export const MAX_SCAN_FILE_SIZE = 10 * 1024 * 1024

const acceptedScanTypes = new Set(['image/jpeg', 'image/png', 'image/webp'])

export function getFirstScanFile(files: FileList | readonly File[] | null | undefined): File | null {
  return files?.[0] ?? null
}

export function validateScanFile(file: Pick<File, 'size' | 'type'>): string | null {
  if (!acceptedScanTypes.has(file.type)) {
    return 'Выберите изображение в формате JPEG, PNG или WebP.'
  }

  if (file.size > MAX_SCAN_FILE_SIZE) {
    return 'Размер фотографии не должен превышать 10 МБ.'
  }

  return null
}
