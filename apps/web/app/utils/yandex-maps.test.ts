import { describe, expect, it } from 'vitest'

import { wineTours } from '#shared/tours/catalog'
import {
  buildYandexMapsOpenUrl,
  buildYandexMapWidgetUrl,
  getRouteMapLocations,
  getTourMapLocations,
} from './yandex-maps'

describe('Yandex wine tour map', () => {
  it('groups programs at the same geographical location', () => {
    const locations = getTourMapLocations(wineTours)

    expect(locations).toHaveLength(8)
    expect(locations.find(location => location.name === 'Новороссийск')?.tours).toHaveLength(2)
    expect(locations.find(location => location.name === 'Новый Свет')?.tours).toHaveLength(3)
  })

  it('keeps the assistant route order and removes duplicate locations', () => {
    const locations = getRouteMapLocations(wineTours, [
      'golden-balka-sparkling',
      'golden-balka-intro',
      'winepark-intro',
    ])

    expect(locations.map(location => location.name)).toEqual(['Балаклава', 'Понизовка'])
  })

  it('builds an automobile route for the Yandex widget', () => {
    const url = new URL(buildYandexMapWidgetUrl(wineTours, [
      'golden-balka-sparkling',
      'winepark-intro',
    ]))

    expect(url.hostname).toBe('yandex.ru')
    expect(url.searchParams.get('rtt')).toBe('auto')
    expect(url.searchParams.get('rtext')).toBe('44.500000,33.600000~44.400000,33.960000')
  })

  it('shows every location before the assistant builds a route', () => {
    const url = new URL(buildYandexMapWidgetUrl(wineTours, []))

    expect(url.searchParams.get('pt')?.split('~')).toHaveLength(8)
    expect(url.searchParams.has('rtext')).toBe(false)
  })

  it('keeps an empty filtered map URL valid without an empty marker parameter', () => {
    const url = new URL(buildYandexMapWidgetUrl([], []))

    expect(url.searchParams.get('z')).toBe('7')
    expect(url.searchParams.has('pt')).toBe(false)
  })

  it('creates a shareable Yandex Maps route link', () => {
    const url = new URL(buildYandexMapsOpenUrl(wineTours, [
      'golden-balka-sparkling',
      'winepark-intro',
    ]))

    expect(url.pathname).toBe('/maps/')
    expect(url.searchParams.get('mode')).toBe('routes')
  })
})
