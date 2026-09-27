<script setup lang="ts">
import { ExternalLink, MapPin } from '@lucide/vue'
import type { WineTour } from '#shared/tours/catalog'
import type {
  TourMapLocation,
  YandexMapsApi,
  YandexMapInstance,
  YandexMultiRoute,
} from '~/utils/yandex-maps'
import {
  buildYandexMapsOpenUrl,
  buildYandexMapWidgetUrl,
  getRouteMapLocations,
  getTourMapLocations,
  loadYandexMaps,
} from '~/utils/yandex-maps'

type MapState = 'idle' | 'loading' | 'ready' | 'widget'

const props = withDefaults(defineProps<{
  tours: readonly WineTour[]
  routeIds?: readonly string[]
}>(), {
  routeIds: () => [],
})

const emit = defineEmits<{
  opened: [tour: WineTour]
}>()

const config = useRuntimeConfig()
const mapContainer = ref<HTMLElement | null>(null)
const mapState = ref<MapState>('idle')
const routeDetails = ref('')
let yandexMaps: YandexMapsApi | null = null
let map: YandexMapInstance | null = null

const locations = computed(() => getTourMapLocations(props.tours))
const routeLocations = computed(() => getRouteMapLocations(props.tours, props.routeIds))
const widgetUrl = computed(() => buildYandexMapWidgetUrl(props.tours, props.routeIds))
const openInYandexUrl = computed(() => buildYandexMapsOpenUrl(props.tours, props.routeIds))
const isLoading = computed(() => mapState.value === 'idle' || mapState.value === 'loading')

const mapTitle = computed(() => {
  const count = routeLocations.value.length
  if (!count) return `${locations.value.length} ${getLocationCountLabel(locations.value.length)} на карте`
  if (count === 1) return '1 остановка'
  if (count >= 2 && count <= 4) return `${count} остановки`
  return `${count} остановок`
})

function getLocationCountLabel(count: number) {
  if (count === 1) return 'винная точка'
  if (count >= 2 && count <= 4) return 'винные точки'
  return 'винных точек'
}

function getTourCountLabel(count: number) {
  if (count === 1) return 'тур'
  if (count >= 2 && count <= 4) return 'тура'
  return 'туров'
}

function getLocationsCenter(mapLocations: readonly TourMapLocation[]): [number, number] {
  if (!mapLocations.length) return [44.8, 35.8]
  const total = mapLocations.reduce(
    (result, location) => [
      result[0] + location.coordinates[0],
      result[1] + location.coordinates[1],
    ] as [number, number],
    [0, 0] as [number, number],
  )
  return [total[0] / mapLocations.length, total[1] / mapLocations.length]
}

function getRouteOrder(location: TourMapLocation) {
  const index = routeLocations.value.findIndex(item => item.key === location.key)
  return index >= 0 ? index + 1 : null
}

function openLocation(location: TourMapLocation) {
  const plannedTour = location.tours.find(tour => props.routeIds.includes(tour.id))
  const tour = plannedTour ?? location.tours[0]
  if (tour) emit('opened', tour)
}

function getMetricText(value: unknown): string | null {
  if (!value || typeof value !== 'object' || !('text' in value) || typeof value.text !== 'string') return null
  return value.text
}

function updateRouteDetails(multiRoute: YandexMultiRoute) {
  const activeRoute = multiRoute.getActiveRoute()
  if (!activeRoute) return
  const distance = getMetricText(activeRoute.properties.get('distance'))
  const duration = getMetricText(activeRoute.properties.get('duration'))
  routeDetails.value = [distance, duration].filter(Boolean).join(' · ')
}

function getCssColor(token: string, fallback: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(token).trim() || fallback
}

function renderMap() {
  if (!map || !yandexMaps) return

  map.geoObjects.removeAll()
  routeDetails.value = ''
  const routeColor = getCssColor('--color-wine', '#8f3d42')
  const defaultPinColor = getCssColor('--color-green-dark', '#4f5935')

  if (routeLocations.value.length > 1) {
    const multiRoute = new yandexMaps.multiRouter.MultiRoute({
      referencePoints: routeLocations.value.map(location => location.coordinates),
      params: { routingMode: 'auto', results: 1 },
    }, {
      boundsAutoApply: true,
      wayPointVisible: false,
      routeActiveStrokeColor: routeColor,
      routeActiveStrokeWidth: 5,
      routeStrokeColor: getCssColor('--color-tour-map-line', '#c9b9aa'),
      routeStrokeWidth: 3,
    })
    multiRoute.model.events.add('requestsuccess', () => updateRouteDetails(multiRoute))
    map.geoObjects.add(multiRoute)
  }
  else if (routeLocations.value[0]) {
    map.setCenter(routeLocations.value[0].coordinates, 10, { duration: 300 })
  }
  else {
    const zoom = locations.value.length === 1 ? 10 : locations.value.length <= 4 ? 8 : 7
    map.setCenter(getLocationsCenter(locations.value), zoom, { duration: 300 })
  }

  for (const location of locations.value) {
    const routeOrder = getRouteOrder(location)
    const placemark = new yandexMaps.Placemark(location.coordinates, {
      hintContent: routeOrder ? `${routeOrder}. ${location.name}` : location.name,
    }, {
      preset: 'islands#circleDotIcon',
      iconColor: routeOrder ? routeColor : defaultPinColor,
    })
    placemark.events.add('click', () => openLocation(location))
    map.geoObjects.add(placemark)
  }
}

async function initializeMap() {
  const apiKey = config.public.yandexMapsApiKey.trim()
  if (!apiKey) {
    mapState.value = 'widget'
    return
  }

  mapState.value = 'loading'
  try {
    yandexMaps = await loadYandexMaps(apiKey)
    const container = mapContainer.value
    if (!container) return
    map = new yandexMaps.Map(container, {
      center: [44.8, 35.8],
      zoom: 7,
      controls: ['zoomControl', 'fullscreenControl'],
    }, {
      suppressMapOpenBlock: true,
      yandexMapDisablePoiInteractivity: true,
    })
    mapState.value = 'ready'
    renderMap()
  }
  catch {
    mapState.value = 'widget'
  }
}

watch([() => props.routeIds.join('|'), () => props.tours.map(tour => tour.id).join('|')], () => {
  if (mapState.value === 'ready') renderMap()
})

onMounted(initializeMap)
onBeforeUnmount(() => map?.destroy())
</script>

<template>
  <section class="route-map" aria-label="Интерактивная Яндекс Карта винного маршрута">
    <div class="route-map__toolbar">
      <div>
        <span>Яндекс Карты · автомобильный маршрут</span>
        <strong>{{ mapTitle }}</strong>
        <small v-if="routeDetails">{{ routeDetails }}</small>
      </div>
      <a :href="openInYandexUrl" target="_blank" rel="noopener noreferrer">
        Открыть
        <ExternalLink :size="17" aria-hidden="true" />
      </a>
    </div>

    <div class="route-map__viewport" :aria-busy="isLoading">
      <div
        ref="mapContainer"
        class="route-map__canvas"
        :class="{ 'route-map__canvas--hidden': mapState === 'widget' }"
      />
      <iframe
        v-if="mapState === 'widget'"
        :key="widgetUrl"
        class="route-map__widget"
        :src="widgetUrl"
        title="Яндекс Карта винного маршрута"
        loading="lazy"
        allowfullscreen
        referrerpolicy="strict-origin-when-cross-origin"
      />
      <div v-if="isLoading" class="route-map__loading" role="status">
        <span />
        <strong>Загружаем карту и дороги…</strong>
      </div>
    </div>

    <div class="route-map__locations" aria-label="Точки на карте">
      <button
        v-for="location in locations"
        :key="location.key"
        type="button"
        :aria-pressed="Boolean(getRouteOrder(location))"
        @click="openLocation(location)"
      >
        <span class="route-map__location-mark">
          {{ getRouteOrder(location) ?? '' }}
          <MapPin v-if="!getRouteOrder(location)" :size="16" aria-hidden="true" />
        </span>
        <span><strong>{{ location.name }}</strong><small>{{ location.tours.length }} {{ getTourCountLabel(location.tours.length) }}</small></span>
      </button>
    </div>

    <p class="route-map__caption">Маршрут строится Яндексом по дорогам. Время и траектория могут меняться из-за пробок.</p>
  </section>
</template>

<style scoped>
.route-map {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--color-tour-map-line);
  border-radius: var(--radius-lg);
  background: var(--color-paper);
  box-shadow: var(--shadow-paper);
}

.route-map__toolbar {
  min-height: 82px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 18px 13px 20px;
  border-bottom: 1px solid var(--color-tour-map-line);
  background: rgb(255 255 255 / 92%);
}

.route-map__toolbar > div {
  min-width: 0;
  display: grid;
}

.route-map__toolbar span {
  color: var(--color-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
}

.route-map__toolbar strong {
  overflow-wrap: anywhere;
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
}

.route-map__toolbar small {
  color: var(--color-wine-dark);
  font-size: 12px;
  font-weight: 700;
}

.route-map__toolbar a {
  min-height: 44px;
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 7px;
  padding: 9px 14px;
  border: 1px solid var(--color-tour-line);
  border-radius: var(--radius-pill);
  color: var(--color-wine-dark);
  background: var(--color-tour-sand);
  font-size: 13px;
  font-weight: 700;
  transition: border-color 160ms ease, background 160ms ease;
}

.route-map__toolbar a:hover {
  border-color: var(--color-wine);
  background: var(--color-soft-wine);
}

.route-map__viewport {
  position: relative;
  min-height: 500px;
  overflow: hidden;
  background: var(--color-tour-sand);
}

.route-map__canvas,
.route-map__widget {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
}

.route-map__canvas--hidden {
  display: none;
}

.route-map__loading {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 14px;
  color: var(--color-muted);
  background:
    linear-gradient(105deg, transparent 35%, rgb(255 255 255 / 78%) 50%, transparent 65%),
    var(--color-tour-sand);
  background-size: 220% 100%;
  animation: map-loading 1.4s ease-in-out infinite;
}

.route-map__loading span {
  width: 44px;
  height: 44px;
  border: 10px solid var(--color-soft-wine);
  border-radius: 50% 50% 50% 0;
  background: var(--color-wine);
  transform: rotate(-45deg);
}

.route-map__loading strong {
  font-size: 14px;
}

.route-map__locations {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--color-tour-map-line);
}

.route-map__locations button {
  min-width: 0;
  min-height: 52px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 9px;
  border: 1px solid var(--color-tour-line);
  border-radius: var(--radius-sm);
  color: var(--color-muted);
  background: var(--color-paper);
  text-align: left;
  cursor: pointer;
}

.route-map__locations button[aria-pressed="true"] {
  border-color: var(--color-wine);
  color: var(--color-wine-dark);
  background: var(--color-soft-wine);
}

.route-map__location-mark {
  width: 30px;
  height: 30px;
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 50%;
  color: var(--color-paper);
  background: var(--color-green-dark);
  font-size: 12px;
  font-weight: 700;
}

button[aria-pressed="true"] .route-map__location-mark {
  background: var(--color-wine);
}

.route-map__locations button > span:last-child {
  min-width: 0;
  display: grid;
}

.route-map__locations strong,
.route-map__locations small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-map__locations strong {
  color: var(--color-ink);
  font-size: 12px;
}

.route-map__locations small {
  font-size: 10px;
}

.route-map__caption {
  min-height: 48px;
  display: flex;
  align-items: center;
  padding: 10px 20px;
  margin: 0;
  border-top: 1px solid var(--color-tour-map-line);
  color: var(--color-muted);
  background: var(--color-tour-sand);
  font-size: 12px;
}

@keyframes map-loading {
  to { background-position: -120% 0; }
}

@media (max-width: 680px) {
  .route-map__toolbar {
    min-height: 76px;
    padding-inline: 14px;
  }

  .route-map__toolbar span {
    max-width: 190px;
    white-space: normal;
  }

  .route-map__toolbar a {
    width: 44px;
    padding-inline: 0;
    justify-content: center;
    font-size: 0;
  }

  .route-map__viewport {
    min-height: 440px;
  }

  .route-map__locations {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (prefers-reduced-motion: reduce) {
  .route-map__loading {
    animation: none;
  }
}
</style>
