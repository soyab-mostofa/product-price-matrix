import { Hono } from 'hono'
import { fetchCatalog } from '../server/catalog'
import type { AppEnv } from '../types'

const products = new Hono<AppEnv>()

products.get('/', async (c) => {
  const catalog = await fetchCatalog(c.env.DB)
  c.header('Cache-Control', 'public, max-age=60, stale-while-revalidate=300')
  return c.json(catalog)
})

export default products
