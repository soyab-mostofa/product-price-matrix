import type { Context, MiddlewareHandler } from 'hono'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import type { AppEnv, EnvBindings } from '../types'

const SESSION_COOKIE = 'price_matrix_admin'
const SESSION_TTL_SECONDS = 12 * 60 * 60
const encoder = new TextEncoder()

function encodeBase64Url(input: ArrayBuffer | Uint8Array | string): string {
  const bytes = typeof input === 'string' ? encoder.encode(input) : new Uint8Array(input instanceof ArrayBuffer ? input : input.buffer)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

function decodeBase64Url(input: string): string {
  const normalized = input.replace(/-/g, '+').replace(/_/g, '/')
  return atob(normalized + '='.repeat((4 - normalized.length % 4) % 4))
}

function constantTimeEqual(left: string, right: string): boolean {
  const length = Math.max(left.length, right.length)
  let mismatch = left.length ^ right.length
  for (let index = 0; index < length; index += 1) {
    mismatch |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0)
  }
  return mismatch === 0
}

async function sign(secret: string, value: string): Promise<string> {
  const key = await crypto.subtle.importKey('raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
  return encodeBase64Url(await crypto.subtle.sign('HMAC', key, encoder.encode(value)))
}

export function authConfigured(env: EnvBindings): env is EnvBindings & { ADMIN_PASSWORD: string; SESSION_SECRET: string } {
  return Boolean(env.ADMIN_PASSWORD && env.SESSION_SECRET)
}

export async function passwordMatches(candidate: string, expected: string): Promise<boolean> {
  const [candidateHash, expectedHash] = await Promise.all([
    crypto.subtle.digest('SHA-256', encoder.encode(candidate)),
    crypto.subtle.digest('SHA-256', encoder.encode(expected)),
  ])
  return constantTimeEqual(encodeBase64Url(candidateHash), encodeBase64Url(expectedHash))
}

export async function createAdminSession(c: Context<AppEnv>): Promise<void> {
  if (!authConfigured(c.env)) throw new Error('Admin authentication is not configured')
  const payload = encodeBase64Url(JSON.stringify({ version: 1, expiresAt: Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS }))
  const token = `${payload}.${await sign(c.env.SESSION_SECRET, payload)}`
  setCookie(c, SESSION_COOKIE, token, {
    httpOnly: true,
    secure: new URL(c.req.url).protocol === 'https:',
    sameSite: 'Strict',
    path: '/',
    maxAge: SESSION_TTL_SECONDS,
  })
}

export function clearAdminSession(c: Context<AppEnv>): void {
  deleteCookie(c, SESSION_COOKIE, { path: '/', secure: new URL(c.req.url).protocol === 'https:' })
}

export async function isAdmin(c: Context<AppEnv>): Promise<boolean> {
  if (!authConfigured(c.env)) return false
  const token = getCookie(c, SESSION_COOKIE)
  if (!token) return false
  const separator = token.lastIndexOf('.')
  if (separator < 1) return false
  const payload = token.slice(0, separator)
  const signature = token.slice(separator + 1)
  if (!constantTimeEqual(signature, await sign(c.env.SESSION_SECRET, payload))) return false
  try {
    const parsed = JSON.parse(decodeBase64Url(payload)) as { version?: number; expiresAt?: number }
    return parsed.version === 1 && Number(parsed.expiresAt) > Math.floor(Date.now() / 1000)
  } catch {
    return false
  }
}

function isSameOriginMutation(c: Context<AppEnv>): boolean {
  const requestOrigin = new URL(c.req.url).origin
  const origin = c.req.header('Origin')
  const referer = c.req.header('Referer')
  if (c.req.header('X-Price-Matrix-Admin') !== '1') return false
  if (origin) return origin === requestOrigin
  if (!referer) return false
  try {
    return new URL(referer).origin === requestOrigin
  } catch {
    return false
  }
}

export const requireAdmin: MiddlewareHandler<AppEnv> = async (c, next) => {
  if (!authConfigured(c.env)) return c.json({ success: false, error: 'Admin authentication is not configured' }, 503)
  if (!isSameOriginMutation(c)) return c.json({ success: false, error: 'Same-origin admin request required' }, 403)
  if (!(await isAdmin(c))) return c.json({ success: false, error: 'Admin authentication required' }, 401)
  await next()
}

export async function loginRateLimitKey(c: Context<AppEnv>): Promise<string> {
  if (!authConfigured(c.env)) throw new Error('Admin authentication is not configured')
  const address = c.req.header('CF-Connecting-IP') ?? 'unknown'
  return sign(c.env.SESSION_SECRET, `login:${address}`)
}
