import { describe, expect, it } from 'vitest'

import { ADMIN_QUERY_MAX_LENGTH, parseAdminQuery } from './catalog-admin'

describe('admin catalog query parsing', () => {
  it('normalizes invalid pages to the first page', () => {
    expect(parseAdminQuery({ page: '0' }).page).toBe(1)
    expect(parseAdminQuery({ page: '-3' }).page).toBe(1)
    expect(parseAdminQuery({ page: 'two' }).page).toBe(1)
    expect(parseAdminQuery({ page: '4' }).page).toBe(4)
  })

  it('trims and limits the search text', () => {
    expect(parseAdminQuery({ q: '  кокур  ' }).q).toBe('кокур')
    expect(parseAdminQuery({ q: 'a'.repeat(500) }).q).toHaveLength(ADMIN_QUERY_MAX_LENGTH)
    expect(parseAdminQuery({ q: ['x'] }).q).toBe('')
  })

  it('accepts only known image statuses', () => {
    expect(parseAdminQuery({ imageStatus: 'suspicious' }).imageStatus).toBe('suspicious')
    expect(parseAdminQuery({ imageStatus: 'indexed' }).imageStatus).toBe('all')
    expect(parseAdminQuery({}).imageStatus).toBe('all')
  })
})
