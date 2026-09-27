export const tourDatePreferences = ['nearest-saturday', 'nearest-sunday', 'decide-later'] as const

export type TourDatePreference = typeof tourDatePreferences[number]

export interface SavedTourPlan {
  tourId: string
  datePreference: TourDatePreference
  guests: number
  savedAt: string
}

const datePreferenceSet = new Set<string>(tourDatePreferences)

export function isSavedTourPlan(value: unknown): value is SavedTourPlan {
  if (!value || typeof value !== 'object') {
    return false
  }

  const plan = value as Record<string, unknown>

  return typeof plan.tourId === 'string'
    && plan.tourId.length > 0
    && typeof plan.datePreference === 'string'
    && datePreferenceSet.has(plan.datePreference)
    && typeof plan.guests === 'number'
    && Number.isInteger(plan.guests)
    && plan.guests >= 1
    && plan.guests <= 8
    && typeof plan.savedAt === 'string'
}

export function parseSavedTourPlans(rawValue: string | null): SavedTourPlan[] {
  if (!rawValue) {
    return []
  }

  try {
    const value: unknown = JSON.parse(rawValue)
    return Array.isArray(value) ? value.filter(isSavedTourPlan) : []
  }
  catch {
    return []
  }
}
