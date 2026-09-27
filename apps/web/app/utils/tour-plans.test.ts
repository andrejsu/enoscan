import { describe, expect, it } from 'vitest'
import { isSavedTourPlan, parseSavedTourPlans } from './tour-plans'

const validPlan = {
  tourId: 'sikory-sunset',
  datePreference: 'nearest-saturday',
  guests: 2,
  savedAt: '2026-09-26T12:00:00.000Z',
}

describe('isSavedTourPlan', () => {
  it('accepts a complete plan', () => {
    expect(isSavedTourPlan(validPlan)).toBe(true)
  })

  it('rejects invalid guest counts and date preferences', () => {
    expect(isSavedTourPlan({ ...validPlan, guests: 0 })).toBe(false)
    expect(isSavedTourPlan({ ...validPlan, guests: 2.5 })).toBe(false)
    expect(isSavedTourPlan({ ...validPlan, datePreference: 'tomorrow' })).toBe(false)
  })
})

describe('parseSavedTourPlans', () => {
  it('keeps only valid plans from local storage', () => {
    const value = JSON.stringify([validPlan, { ...validPlan, tourId: '', guests: 12 }])

    expect(parseSavedTourPlans(value)).toEqual([validPlan])
  })

  it('returns an empty list for missing or malformed storage', () => {
    expect(parseSavedTourPlans(null)).toEqual([])
    expect(parseSavedTourPlans('{broken')).toEqual([])
  })
})
