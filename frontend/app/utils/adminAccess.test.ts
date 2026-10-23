import { describe, expect, it } from 'vitest'
import { hasAdminAccess, isAdminRoute } from './adminAccess'

describe('isAdminRoute', () => {
  it.each(['/', '/users', '/users/abc', '/roles', '/roles/1', '/applications', '/applications/2', '/audit', '/sessions', '/otra-nueva'])(
    '%s es administrativa', path => expect(isAdminRoute(path)).toBe(true)
  )
  it.each(['/profile', '/profile/', '/sin-acceso', '/leo/forbidden'])(
    '%s no lo es', path => expect(isAdminRoute(path)).toBe(false)
  )
  it('no confunde prefijos parecidos', () => {
    expect(isAdminRoute('/profiles')).toBe(true)
    expect(isAdminRoute('/leopardo')).toBe(true)
  })
})

describe('hasAdminAccess', () => {
  it('requiere algún leo.*', () => {
    expect(hasAdminAccess(['leo.users.view'])).toBe(true)
    expect(hasAdminAccess(['acuarius.paciente.view', 'vladimir.x.view'])).toBe(false)
    expect(hasAdminAccess([])).toBe(false)
    expect(hasAdminAccess(null)).toBe(false)
  })
})
