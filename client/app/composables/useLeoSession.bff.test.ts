import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useLeoSession } from './useLeoSession'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn(async (to: unknown) => to) }))
mockNuxtImport('navigateTo', () => navigateToMock)

const logout = vi.fn(async () => {})
const login = vi.fn(async () => ({ url: 'http://leo.test/authorize?dpop_jkt=k', external: true }))

beforeEach(() => {
  navigateToMock.mockClear()
  logout.mockClear()
  login.mockClear()
  useState('leo-session').value = {
    status: 'authenticated',
    me: {
      user: { id: 'u', username: 'ana', email: '', first_name: 'Ana', last_name: '' },
      session: { id: 's', expires_at: '', last_activity_at: '', idle_timeout_seconds: 1800 },
      permissions: ['vladimir.samples.view'],
      applications: []
    }
  }
  Object.assign(useNuxtApp().$leo.transport, { kind: 'bff', logout, login })
})

describe('useLeoSession con transporte bff', () => {
  it('can() usa los permisos del SDK', () => {
    const session = useLeoSession()
    expect(session.can('vladimir.samples.view')).toBe(true)
    expect(session.can('vladimir.samples.edit')).toBe(false)
  })

  it('logout: POST /auth/logout, limpia el estado y navega al login de Leo', async () => {
    const session = useLeoSession()
    await session.logout()
    expect(logout).toHaveBeenCalledTimes(1)
    expect(session.isAuthenticated.value).toBe(false)
    expect(login).toHaveBeenCalledWith('/', undefined)
    expect(navigateToMock).toHaveBeenCalledWith('http://leo.test/authorize?dpop_jkt=k', { external: true, replace: true })
  })
})
