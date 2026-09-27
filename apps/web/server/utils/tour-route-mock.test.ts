import { describe, expect, it } from 'vitest'

import { wineTours } from '#shared/tours/catalog'
import { createMockTourRouteResponse } from './tour-route-mock'

describe('mock tour route assistant', () => {
  it('builds a grounded Crimea route within the stated budget', () => {
    const result = createMockTourRouteResponse([
      { role: 'user', content: 'Хочу винный маршрут по Крыму на 2 дня, бюджет до 6 тысяч рублей' },
    ])

    expect(result.status).toBe('planned')
    expect(result.route?.tourIds.length).toBeGreaterThan(1)
    expect(result.route?.estimatedPricePerPerson).toBeLessThanOrEqual(6000)
    expect(result.route?.tourIds.every((id) => {
      const tour = wineTours.find(item => item.id === id)
      return tour?.region === 'crimea'
    })).toBe(true)
    const longitudes = result.route?.tourIds.map((id) => (
      wineTours.find(tour => tour.id === id)?.coordinates.lng ?? 0
    )) ?? []
    expect(longitudes).toEqual([...longitudes].sort((first, second) => first - second))
  })

  it('prioritizes a sunset when the user asks for it', () => {
    const result = createMockTourRouteResponse([
      { role: 'user', content: 'Построй маршрут по винодельням Краснодарского края с закатом' },
    ])

    expect(result.route?.tourIds[0]).toBe('sikory-sunset')
  })

  it('keeps a one-day request to one local program', () => {
    const result = createMockTourRouteResponse([
      { role: 'user', content: 'Один день под Новороссийском с красивым закатом' },
    ])

    expect(result.route?.tourIds).toEqual(['sikory-sunset'])
    expect(result.route?.estimatedPricePerPerson).toBe(6000)
    expect(result.message).toContain('одну точку на карте')
  })

  it('finds the real underground Inkerman program by experience', () => {
    const result = createMockTourRouteResponse([
      { role: 'user', content: 'Хочу один день по подземным погребам до 3 тысяч' },
    ])

    expect(result.route?.tourIds).toEqual(['inkerman-underground'])
    expect(result.route?.estimatedPricePerPerson).toBe(1200)
  })

  it('asks for travel constraints after a greeting', () => {
    const result = createMockTourRouteResponse([{ role: 'user', content: 'Привет' }])

    expect(result.status).toBe('clarification')
    expect(result.route).toBeNull()
  })
})
