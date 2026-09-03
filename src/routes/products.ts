import { Hono } from 'hono'
import { fetchCatalog } from '../server/catalog'
import { type AppEnv, isSourcingOrigin } from '../types'

const products = new Hono<AppEnv>()

products.get('/', async (c) => {
  // An unrecognised origin is a caller bug; serving the whole catalog instead
  // would quietly mix the two books together.
  const requested = c.req.query('origin') ?? 'local'
  if (!isSourcingOrigin(requested)) {
    return c.json({ success: false, error: 'Unknown sourcing origin' }, 400)
  }
  const catalog = await fetchCatalog(c.env.DB, requested)
  c.header('Cache-Control', 'public, max-age=60, stale-while-revalidate=300')
  return c.json(catalog)
})

export default products
