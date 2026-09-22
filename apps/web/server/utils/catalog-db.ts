import { Pool } from 'pg'

let catalogPool: Pool | undefined

export function getCatalogPool(databaseUrl: string): Pool {
  catalogPool ??= new Pool({
    connectionString: databaseUrl || undefined,
    max: 5,
    idleTimeoutMillis: 30_000,
  })
  return catalogPool
}
