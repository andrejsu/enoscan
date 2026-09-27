import type { WineTour } from '#shared/tours/catalog'

export type YandexCoordinates = [latitude: number, longitude: number]

export interface TourMapLocation {
  key: string
  name: string
  tours: WineTour[]
  coordinates: YandexCoordinates
}

interface YandexEventManager {
  add: (eventName: string, handler: () => void) => void
}

interface YandexGeoObjectCollection {
  add: (object: object) => YandexGeoObjectCollection
  removeAll: () => void
}

interface YandexPropertyManager {
  get: (propertyName: string) => unknown
}

interface YandexActiveRoute {
  properties: YandexPropertyManager
}

export interface YandexMapInstance {
  geoObjects: YandexGeoObjectCollection
  destroy: () => void
  setCenter: (coordinates: YandexCoordinates, zoom?: number, options?: Record<string, unknown>) => void
}

export interface YandexPlacemark {
  events: YandexEventManager
}

export interface YandexMultiRoute {
  model: { events: YandexEventManager }
  getActiveRoute: () => YandexActiveRoute | null
}

export interface YandexMapsApi {
  ready: (callback: () => void) => void
  Map: new (
    container: HTMLElement,
    state: { center: YandexCoordinates, zoom: number, controls?: string[] },
    options?: Record<string, unknown>,
  ) => YandexMapInstance
  Placemark: new (
    geometry: YandexCoordinates,
    properties?: Record<string, unknown>,
    options?: Record<string, unknown>,
  ) => YandexPlacemark
  multiRouter: {
    MultiRoute: new (
      model: { referencePoints: YandexCoordinates[], params?: Record<string, unknown> },
      options?: Record<string, unknown>,
    ) => YandexMultiRoute
  }
}

declare global {
  interface Window {
    ymaps?: YandexMapsApi
  }
}

const yandexMapsScriptId = 'yandex-maps-api'
let yandexMapsLoader: Promise<YandexMapsApi> | null = null

function waitForYandexMaps(resolve: (api: YandexMapsApi) => void, reject: (error: Error) => void) {
  const api = window.ymaps
  if (!api) {
    reject(new Error('Yandex Maps API did not initialize.'))
    return
  }
  api.ready(() => resolve(api))
}

export function loadYandexMaps(apiKey: string): Promise<YandexMapsApi> {
  if (!import.meta.client) return Promise.reject(new Error('Yandex Maps API is available only in the browser.'))

  const loadedApi = window.ymaps
  if (loadedApi) return new Promise(resolve => loadedApi.ready(() => resolve(loadedApi)))
  if (yandexMapsLoader) return yandexMapsLoader

  yandexMapsLoader = new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(() => reject(new Error('Yandex Maps API loading timed out.')), 15_000)
    const handleLoad = () => {
      window.clearTimeout(timeoutId)
      waitForYandexMaps(resolve, reject)
    }
    const handleError = () => {
      window.clearTimeout(timeoutId)
      reject(new Error('Yandex Maps API failed to load.'))
    }

    const existingScript = document.getElementById(yandexMapsScriptId)
    if (existingScript instanceof HTMLScriptElement) {
      existingScript.addEventListener('load', handleLoad, { once: true })
      existingScript.addEventListener('error', handleError, { once: true })
      return
    }

    const script = document.createElement('script')
    script.id = yandexMapsScriptId
    script.async = true
    script.src = `https://api-maps.yandex.ru/2.1/?apikey=${encodeURIComponent(apiKey)}&lang=ru_RU`
    script.addEventListener('load', handleLoad, { once: true })
    script.addEventListener('error', handleError, { once: true })
    document.head.append(script)
  })

  return yandexMapsLoader
}

export function getTourMapLocations(tours: readonly WineTour[]): TourMapLocation[] {
  const grouped = new Map<string, TourMapLocation>()
  for (const tour of tours) {
    const current = grouped.get(tour.location)
    if (current) {
      current.tours.push(tour)
      continue
    }
    grouped.set(tour.location, {
      key: tour.location,
      name: tour.location,
      tours: [tour],
      coordinates: [tour.coordinates.lat, tour.coordinates.lng],
    })
  }
  return [...grouped.values()]
}

export function getRouteMapLocations(
  tours: readonly WineTour[],
  routeIds: readonly string[],
): TourMapLocation[] {
  const locations = getTourMapLocations(tours)
  const locationsByTourId = new Map(locations.flatMap(location => (
    location.tours.map(tour => [tour.id, location] as const)
  )))
  const usedLocations = new Set<string>()

  return routeIds.flatMap((tourId) => {
    const location = locationsByTourId.get(tourId)
    if (!location || usedLocations.has(location.key)) return []
    usedLocations.add(location.key)
    return [location]
  })
}

function coordinateText([latitude, longitude]: YandexCoordinates) {
  return `${latitude.toFixed(6)},${longitude.toFixed(6)}`
}

function markerText([latitude, longitude]: YandexCoordinates) {
  return `${longitude.toFixed(6)},${latitude.toFixed(6)},pm2rdm`
}

function averageCoordinates(locations: readonly TourMapLocation[]): YandexCoordinates {
  if (!locations.length) return [44.8, 35.8]
  const total = locations.reduce(
    (result, location) => [
      result[0] + location.coordinates[0],
      result[1] + location.coordinates[1],
    ] as YandexCoordinates,
    [0, 0] as YandexCoordinates,
  )
  return [total[0] / locations.length, total[1] / locations.length]
}

export function buildYandexMapWidgetUrl(
  tours: readonly WineTour[],
  routeIds: readonly string[],
): string {
  const allLocations = getTourMapLocations(tours)
  const routeLocations = getRouteMapLocations(tours, routeIds)
  const displayedLocations = routeLocations.length ? routeLocations : allLocations
  const [latitude, longitude] = averageCoordinates(displayedLocations)
  const params = new URLSearchParams({
    lang: 'ru_RU',
    l: 'map',
    ll: `${longitude.toFixed(6)},${latitude.toFixed(6)}`,
  })

  if (routeLocations.length > 1) {
    params.set('rtext', routeLocations.map(location => coordinateText(location.coordinates)).join('~'))
    params.set('rtt', 'auto')
  }
  else if (displayedLocations.length) {
    const zoom = displayedLocations.length === 1 ? '10' : displayedLocations.length <= 4 ? '8' : '7'
    params.set('z', zoom)
    params.set('pt', displayedLocations.map(location => markerText(location.coordinates)).join('~'))
  }
  else {
    params.set('z', '7')
  }

  return `https://yandex.ru/map-widget/v1/?${params.toString()}`
}

export function buildYandexMapsOpenUrl(
  tours: readonly WineTour[],
  routeIds: readonly string[],
): string {
  const routeLocations = getRouteMapLocations(tours, routeIds)
  const params = new URLSearchParams()

  if (routeLocations.length > 1) {
    params.set('mode', 'routes')
    params.set('rtext', routeLocations.map(location => coordinateText(location.coordinates)).join('~'))
    params.set('rtt', 'auto')
  }
  else {
    const displayedLocations = routeLocations.length ? routeLocations : getTourMapLocations(tours)
    const [latitude, longitude] = averageCoordinates(displayedLocations)
    params.set('ll', `${longitude.toFixed(6)},${latitude.toFixed(6)}`)
    const zoom = displayedLocations.length === 1 ? '10' : displayedLocations.length <= 4 ? '8' : '7'
    params.set('z', zoom)
    if (displayedLocations.length) {
      params.set('pt', displayedLocations.map(location => markerText(location.coordinates)).join('~'))
    }
  }

  return `https://yandex.ru/maps/?${params.toString()}`
}
