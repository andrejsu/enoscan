import { describe, expect, it } from 'vitest'
import { isScannerRestart } from './scanner-nav'

describe('isScannerRestart', () => {
  it('restarts when the scanner link is clicked on the scanner page', () => {
    expect(isScannerRestart('/', '/')).toBe(true)
  })

  it('navigates normally from another page', () => {
    expect(isScannerRestart('/', '/pairings')).toBe(false)
  })

  it('ignores links to other sections', () => {
    expect(isScannerRestart('/tours', '/')).toBe(false)
  })
})
