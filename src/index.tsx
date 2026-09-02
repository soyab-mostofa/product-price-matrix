import { Hono } from 'hono'
import { Header } from './components/Header'
import { Layout } from './components/Layout'
import { Modals } from './components/Modals'
import { PriceMatrix } from './components/PriceMatrix'
import auth from './routes/auth'
import engine from './routes/engine'
import overrides from './routes/overrides'
import products from './routes/products'
import { fetchDashboardMeta } from './server/catalog'
import type { AppEnv } from './types'

const app = new Hono<AppEnv>()

app.route('/api/auth', auth)
app.route('/api/products', products)
app.route('/api/engine', engine)
app.route('/api/overrides', overrides)

app.get('/', async (c) => {
  const meta = await fetchDashboardMeta(c.env.DB)
  return c.html(
    <Layout>
      <Header meta={meta} />
      <PriceMatrix />
      <Modals />
    </Layout>,
  )
})

export default app
