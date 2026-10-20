import { describe, expect, it } from 'vitest'
import { hasPermission } from './permissions'

const granted = ['leo.users.view', 'leo.users.create', 'leo.roles.view']

describe('hasPermission', () => {
  it('true si el usuario tiene el tag', () => {
    expect(hasPermission(granted, 'leo.users.view')).toBe(true)
  })

  it('false si no lo tiene (coincidencia exacta, sin prefijos ni comodines)', () => {
    expect(hasPermission(granted, 'leo.users.edit')).toBe(false)
    expect(hasPermission(granted, 'leo.users')).toBe(false)
    expect(hasPermission(granted, 'leo.users.*')).toBe(false)
    expect(hasPermission(granted, 'LEO.USERS.VIEW')).toBe(false)
  })

  it('varios tags: por defecto exige todos', () => {
    expect(hasPermission(granted, ['leo.users.view', 'leo.roles.view'])).toBe(true)
    expect(hasPermission(granted, ['leo.users.view', 'leo.audit.view'])).toBe(false)
  })

  it('modo any: basta uno', () => {
    expect(hasPermission(granted, ['leo.audit.view', 'leo.roles.view'], 'any')).toBe(true)
    expect(hasPermission(granted, ['leo.audit.view', 'leo.audit.export'], 'any')).toBe(false)
  })

  it('niega por defecto: sin permisos, sin tags o con lista vacía', () => {
    expect(hasPermission([], 'leo.users.view')).toBe(false)
    expect(hasPermission(granted, [])).toBe(false)
    expect(hasPermission(granted, [], 'any')).toBe(false)
    expect(hasPermission(granted, '')).toBe(false)
    expect(hasPermission(null, 'leo.users.view')).toBe(false)
  })

  it('acepta un Set de permisos', () => {
    expect(hasPermission(new Set(granted), 'leo.roles.view')).toBe(true)
  })
})
