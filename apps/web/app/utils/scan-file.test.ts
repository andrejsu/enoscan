import { describe, expect, it } from 'vitest'
import { getFirstScanFile, MAX_SCAN_FILE_SIZE, validateScanFile } from './scan-file'

describe('getFirstScanFile', () => {
  it('returns the first file from a dropped collection', () => {
    const first = new File(['label'], 'wine-label.jpg', { type: 'image/jpeg' })
    const second = new File(['bottle'], 'bottle.png', { type: 'image/png' })

    expect(getFirstScanFile([first, second])).toBe(first)
  })

  it('returns null when no file was supplied', () => {
    expect(getFirstScanFile([])).toBeNull()
    expect(getFirstScanFile(null)).toBeNull()
  })
})

describe('validateScanFile', () => {
  it('accepts supported images within the limit', () => {
    expect(validateScanFile({ type: 'image/jpeg', size: 1_024 })).toBeNull()
  })

  it('rejects unsupported formats', () => {
    expect(validateScanFile({ type: 'image/gif', size: 1_024 })).toContain('JPEG')
  })

  it('rejects images larger than the limit', () => {
    expect(validateScanFile({ type: 'image/png', size: MAX_SCAN_FILE_SIZE + 1 })).toContain('10 МБ')
  })
})
