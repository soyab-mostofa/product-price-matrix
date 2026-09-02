import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'
import { authConfigured, clearAdminSession, createAdminSession, isAdmin, loginRateLimitKey, passwordMatches } from '../server/auth'
import type { AppEnv } from '../types'

const auth = new Hono<AppEnv>()
const loginSchema = z.object({ password: z.string().min(1).max(512) })
const MAX_FAILURES = 5
const WINDOW_SECONDS = 15 * 60

export const FAILED_LOGIN_SQL = `INSERT INTO admin_login_attempts
  (client_key, failed_attempts, window_started, locked_until, updated_at)
VALUES (?, 1, CURRENT_TIMESTAMP, NULL, CURRENT_TIMESTAMP)
ON CONFLICT(client_key) DO UPDATE SET
  failed_attempts = CASE
    WHEN unixepoch('now') - unixepoch(admin_login_attempts.window_started) >= ? THEN 1
    ELSE admin_login_attempts.failed_attempts + 1
  END,
  window_started = CASE
    WHEN unixepoch('now') - unixepoch(admin_login_attempts.window_started) >= ? THEN CURRENT_TIMESTAMP
    ELSE admin_login_attempts.window_started
  END,
  locked_until = CASE
    WHEN admin_login_attempts.locked_until IS NOT NULL
     AND unixepoch(admin_login_attempts.locked_until) > unixepoch('now')
      THEN admin_login_attempts.locked_until
    WHEN (CASE
      WHEN unixepoch('now') - unixepoch(admin_login_attempts.window_started) >= ? THEN 1
      ELSE admin_login_attempts.failed_attempts + 1
    END) >= ? THEN datetime('now', '+' || ? || ' seconds')
    ELSE NULL
  END,
  updated_at = CURRENT_TIMESTAMP
RETURNING failed_attempts, unixepoch(window_started) AS window_started,
          unixepoch(locked_until) AS locked_until`

interface LoginAttempt {
  failed_attempts: number
  window_started: number | null
  locked_until: number | null
}

auth.get('/', async (c) => c.json({
  success: true,
  configured: authConfigured(c.env),
  authenticated: await isAdmin(c),
}))

auth.post('/', zValidator('json', loginSchema), async (c) => {
  if (!authConfigured(c.env)) return c.json({ success: false, error: 'Admin authentication is not configured' }, 503)
  const origin = c.req.header('Origin')
  if (origin !== new URL(c.req.url).origin || c.req.header('X-Price-Matrix-Admin') !== '1') {
    return c.json({ success: false, error: 'Same-origin admin request required' }, 403)
  }

  const key = await loginRateLimitKey(c)
  const now = Math.floor(Date.now() / 1000)
  const current = await c.env.DB.prepare(
    `SELECT failed_attempts, unixepoch(window_started) AS window_started,
            unixepoch(locked_until) AS locked_until
       FROM admin_login_attempts WHERE client_key = ?`,
  ).bind(key).first<LoginAttempt>()
  if (current?.locked_until && current.locked_until > now) {
    c.header('Retry-After', String(current.locked_until - now))
    return c.json({ success: false, error: 'Too many failed attempts. Try again later.' }, 429)
  }

  const { password } = c.req.valid('json')
  if (!(await passwordMatches(password, c.env.ADMIN_PASSWORD))) {
    const attempt = await c.env.DB.prepare(FAILED_LOGIN_SQL)
      .bind(key, WINDOW_SECONDS, WINDOW_SECONDS, WINDOW_SECONDS, MAX_FAILURES, WINDOW_SECONDS)
      .first<LoginAttempt>()
    const lockedUntil = attempt?.locked_until ?? null
    if (lockedUntil && lockedUntil > now) c.header('Retry-After', String(lockedUntil - now))
    return c.json({ success: false, error: lockedUntil ? 'Too many failed attempts. Try again later.' : 'Invalid password' }, lockedUntil ? 429 : 401)
  }

  await c.env.DB.prepare('DELETE FROM admin_login_attempts WHERE client_key = ?').bind(key).run()
  await createAdminSession(c)
  return c.json({ success: true, authenticated: true })
})

auth.delete('/', async (c) => {
  clearAdminSession(c)
  return c.json({ success: true, authenticated: false })
})

export default auth
