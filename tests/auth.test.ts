import { describe, expect, test } from 'bun:test'
import { Database } from 'bun:sqlite'
import { FAILED_LOGIN_SQL } from '../src/routes/auth'
import { passwordMatches } from '../src/server/auth'

describe('admin authentication helpers', () => {
  test('compares passwords exactly', async () => {
    expect(await passwordMatches('correct horse battery staple', 'correct horse battery staple')).toBe(true)
    expect(await passwordMatches('Correct horse battery staple', 'correct horse battery staple')).toBe(false)
    expect(await passwordMatches('wrong', 'correct horse battery staple')).toBe(false)
  })

  test('atomically locks the fifth failed login attempt', () => {
    const db = new Database(':memory:')
    db.run(`CREATE TABLE admin_login_attempts (
      client_key TEXT PRIMARY KEY,
      failed_attempts INTEGER NOT NULL DEFAULT 0,
      window_started DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      locked_until DATETIME,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )`)
    const statement = db.query<{ failed_attempts: number; locked_until: number | null }, [string, number, number, number, number, number]>(FAILED_LOGIN_SQL)
    const attempts = Array.from({ length: 5 }, () =>
      statement.get('client', 900, 900, 900, 5, 900),
    )

    expect(attempts.map((attempt) => attempt?.failed_attempts)).toEqual([1, 2, 3, 4, 5])
    expect(attempts.slice(0, 4).every((attempt) => attempt?.locked_until === null)).toBe(true)
    expect(attempts[4]?.locked_until).toBeGreaterThan(Math.floor(Date.now() / 1000))
    db.close()
  })
})
