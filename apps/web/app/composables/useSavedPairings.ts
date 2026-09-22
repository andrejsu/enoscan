import type { SavedPairing } from '#shared/contracts'

const storageKey = 'vinolog:saved-pairings:v1'

function isSavedPairing(value: unknown): value is SavedPairing {
  if (!value || typeof value !== 'object') {
    return false
  }

  const item = value as Record<string, unknown>
  const wine = item.wine

  return typeof item.id === 'string'
    && typeof item.dish === 'string'
    && (item.preference === 'softer' || item.preference === 'richer')
    && typeof item.verdict === 'string'
    && typeof item.savedAt === 'string'
    && typeof wine === 'object'
    && wine !== null
    && typeof (wine as Record<string, unknown>).slug === 'string'
    && typeof (wine as Record<string, unknown>).name === 'string'
    && typeof (wine as Record<string, unknown>).producer === 'string'
}

export function useSavedPairings() {
  const pairings = useState<SavedPairing[]>('saved-pairings', () => [])
  const isLoaded = useState('saved-pairings-loaded', () => false)

  function load() {
    if (!import.meta.client || isLoaded.value) {
      return
    }

    try {
      const value: unknown = JSON.parse(localStorage.getItem(storageKey) || '[]')
      pairings.value = Array.isArray(value) ? value.filter(isSavedPairing) : []
    }
    catch {
      pairings.value = []
    }

    isLoaded.value = true
  }

  function save(pairing: SavedPairing) {
    pairings.value = [pairing, ...pairings.value.filter(item => item.id !== pairing.id)]

    if (import.meta.client) {
      localStorage.setItem(storageKey, JSON.stringify(pairings.value))
    }
  }

  onMounted(load)

  return {
    pairings: readonly(pairings),
    isLoaded: readonly(isLoaded),
    save,
  }
}
