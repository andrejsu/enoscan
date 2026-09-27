import type { SavedTourPlan, TourDatePreference } from '~/utils/tour-plans'
import { parseSavedTourPlans } from '~/utils/tour-plans'

const storageKey = 'vinolog:tour-plans:v1'

interface SaveTourPlanInput {
  tourId: string
  datePreference: TourDatePreference
  guests: number
}

export function useTourPlans() {
  const plans = useState<SavedTourPlan[]>('tour-plans', () => [])
  const isLoaded = useState('tour-plans-loaded', () => false)

  const plannedTourIds = computed(() => new Set(plans.value.map(plan => plan.tourId)))

  function load() {
    if (!import.meta.client || isLoaded.value) {
      return
    }

    plans.value = parseSavedTourPlans(localStorage.getItem(storageKey))
    isLoaded.value = true
  }

  function persist() {
    if (import.meta.client) {
      localStorage.setItem(storageKey, JSON.stringify(plans.value))
    }
  }

  function save(input: SaveTourPlanInput) {
    const plan: SavedTourPlan = {
      ...input,
      savedAt: new Date().toISOString(),
    }

    plans.value = [plan, ...plans.value.filter(item => item.tourId !== input.tourId)]
    persist()
  }

  function remove(tourId: string) {
    plans.value = plans.value.filter(plan => plan.tourId !== tourId)
    persist()
  }

  function getPlan(tourId: string) {
    return plans.value.find(plan => plan.tourId === tourId)
  }

  onMounted(load)

  return {
    plans: readonly(plans),
    isLoaded: readonly(isLoaded),
    plannedTourIds,
    save,
    remove,
    getPlan,
  }
}
