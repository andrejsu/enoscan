import type { SavedPairing } from '#shared/contracts'
import { restorePairing } from '~/utils/pairings'

const storageKey = 'vinolog:saved-pairings:v1'

export function useSavedPairings() {
  const pairings = useState<SavedPairing[]>('saved-pairings', () => [])
  const isLoaded = useState('saved-pairings-loaded', () => false)

  function load() {
    if (!import.meta.client || isLoaded.value) {
      return
    }

    try {
      const value: unknown = JSON.parse(localStorage.getItem(storageKey) || '[]')
      pairings.value = Array.isArray(value)
        ? value.map(restorePairing).filter((pairing): pairing is SavedPairing => pairing !== null)
        : []
    }
    catch {
      pairings.value = []
    }

    isLoaded.value = true
  }

  function persist(next: SavedPairing[]) {
    pairings.value = next

    if (import.meta.client) {
      localStorage.setItem(storageKey, JSON.stringify(next))
    }
  }

  function save(pairing: SavedPairing) {
    persist([pairing, ...pairings.value.filter(item => item.id !== pairing.id)])
  }

  function remove(id: string) {
    persist(pairings.value.filter(item => item.id !== id))
  }

  onMounted(load)

  return {
    pairings: readonly(pairings),
    isLoaded: readonly(isLoaded),
    remove,
    save,
  }
}
