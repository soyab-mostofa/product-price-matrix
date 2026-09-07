import { Hono, type Context } from 'hono'
import { Header } from './components/Header'
import { Layout } from './components/Layout'
import { Modals } from './components/Modals'
import { PriceMatrix } from './components/PriceMatrix'
import auth from './routes/auth'
import engine from './routes/engine'
import exportWorkbook from './routes/export'
import overrides from './routes/overrides'
import prices from './routes/prices'
import products from './routes/products'
import { fetchDashboardMeta } from './server/catalog'
import type { AppEnv, SourcingOrigin } from './types'

const app = new Hono<AppEnv>()

app.route('/api/auth', auth)
app.route('/api/products', products)
app.route('/api/engine', engine)
app.route('/api/export.xlsx', exportWorkbook)
app.route('/api/overrides', overrides)
app.route('/api/prices', prices)

/** Both books render the same matrix; only the dataset behind it differs. */
const dashboard = (origin: SourcingOrigin) => async (c: Context<AppEnv>) => {
  const meta = await fetchDashboardMeta(c.env.DB, origin)
  return c.html(
    <Layout>
      <Header meta={meta} />
      <PriceMatrix />
      <Modals />
    </Layout>,
  )
}

app.get('/', dashboard('local'))
app.get('/imported', dashboard('imported'))

export default app
