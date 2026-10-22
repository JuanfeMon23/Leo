import { describe, expect, it } from 'vitest'
import { appInitial, buildProfileUrl, userDisplayName, userInitials } from './userMenu'

const user = (over: Record<string, string | undefined> = {}) => ({
  id: 'u1', username: 'ana', email: 'ana@x.co', first_name: '', last_name: '', ...over
})

describe('userDisplayName', () => {
  it('prefiere nombre y apellido, luego name, luego username', () => {
    expect(userDisplayName(user({ first_name: 'Ana', last_name: 'Pérez' }))).toBe('Ana Pérez')
    expect(userDisplayName(user({ name: 'Ana Pérez' }))).toBe('Ana Pérez')
    expect(userDisplayName(user({ first_name: 'Ana' }))).toBe('Ana')
    expect(userDisplayName(user())).toBe('ana')
  })
  it('sin usuario devuelve vacío', () => {
    expect(userDisplayName(null)).toBe('')
  })
})

describe('userInitials', () => {
  it('dos iniciales con dos o más palabras', () => {
    expect(userInitials('Ana Pérez')).toBe('AP')
    expect(userInitials('Ana María Pérez López')).toBe('AM')
  })
  it('una inicial con una palabra', () => {
    expect(userInitials('ana')).toBe('A')
  })
  it('vacío o espacios devuelve "?"', () => {
    expect(userInitials('')).toBe('?')
    expect(userInitials('   ')).toBe('?')
  })
  it('respeta acentos y mayúsculas', () => {
    expect(userInitials('álvaro ñúñez')).toBe('ÁÑ')
  })
})

describe('buildProfileUrl', () => {
  it('leo-direct: ruta interna', () => {
    expect(buildProfileUrl({ transport: 'leo-direct', leoUrl: '' }, 'http://x/a')).toBe('/profile')
  })
  it('bff: URL de Leo con return codificado', () => {
    expect(buildProfileUrl({ transport: 'bff', leoUrl: 'http://localhost:3100' }, 'http://localhost:3200/a?b=1&c=2'))
      .toBe('http://localhost:3100/profile?return=http%3A%2F%2Flocalhost%3A3200%2Fa%3Fb%3D1%26c%3D2')
  })
  it('bff: ignora la barra final de leoUrl', () => {
    expect(buildProfileUrl({ transport: 'bff', leoUrl: 'http://localhost:3100/' }, 'http://a/'))
      .toBe('http://localhost:3100/profile?return=http%3A%2F%2Fa%2F')
  })
  it('bff sin leoUrl: null', () => {
    expect(buildProfileUrl({ transport: 'bff', leoUrl: '' }, 'http://a/')).toBeNull()
    expect(buildProfileUrl({ transport: 'bff', leoUrl: '  ' }, 'http://a/')).toBeNull()
  })
  it('bff: leoUrl no http(s) se descarta', () => {
    expect(buildProfileUrl({ transport: 'bff', leoUrl: 'javascript:alert(1)' }, 'http://a/')).toBeNull()
  })
})

describe('appInitial', () => {
  it('primera letra en mayúscula', () => {
    expect(appInitial('vladimir')).toBe('V')
    expect(appInitial('  álamo')).toBe('Á')
  })
  it('sin nombre: ?', () => {
    expect(appInitial('')).toBe('?')
    expect(appInitial('   ')).toBe('?')
  })
})
