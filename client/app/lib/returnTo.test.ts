import { describe, expect, it } from 'vitest'
import { safeReturnTo } from './returnTo'

describe('safeReturnTo', () => {
  it('acepta rutas internas con query y fragmento', () => {
    expect(safeReturnTo('/users?page=2#x')).toBe('/users?page=2#x')
    expect(safeReturnTo('/authorize?client_id=a&state=b')).toBe('/authorize?client_id=a&state=b')
  })

  it('rechaza URLs externas o ambiguas (open redirect) y usa el fallback', () => {
    for (const bad of ['https://evil.test', '//evil.test', '/\\evil.test', '\\\\evil.test', '/%5Cevil.test', 'javascript:alert(1)', 'users', '', '/%2F%2Fevil.test', ' /x']) {
      expect(safeReturnTo(bad)).toBe('/')
    }
  })

  it('acepta solo strings (la query puede traer arrays)', () => {
    expect(safeReturnTo(['/a', '/b'])).toBe('/')
    expect(safeReturnTo(undefined, '/inicio')).toBe('/inicio')
  })
})
