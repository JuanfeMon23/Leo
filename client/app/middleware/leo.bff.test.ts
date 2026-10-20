import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RouteLocationNormalized } from 'vue-router'
import middleware from './leo.global'
import { LeoApiError } from '../lib/errors'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn((to: unknown) => to) }))
mockNuxtImport('navigateTo', () => navigateToMock)

const route = (fullPath: string, leo?: Record<string, unknown>) =>
  ({ fullPath, path: fullPath.split('?')[0], meta: leo === undefined ? {} : { leo } }) as unknown as RouteLocationNormalized

const login = vi.fn()

beforeEach(() => {
  navigateToMock.mockClear()
  login.mockReset()
  useState('leo-session').value = { status: 'anonymous', me: null }
  Object.assign(useNuxtApp().$leo.transport, { kind: 'bff', login })
})

describe('middleware leo.global con transporte bff', () => {
  it('sin sesión: pide la authorize_url y navega fuera de la app', async () => {
    login.mockResolvedValue({ url: 'http://leo.test/authorize?dpop_jkt=k', external: true })
    await middleware(route('/muestras?page=2'), route('/'))
    expect(login).toHaveBeenCalledWith('/muestras?page=2')
    expect(navigateToMock).toHaveBeenCalledWith('http://leo.test/authorize?dpop_jkt=k', { external: true, replace: true })
  })

  it('si el backend no responde al pedir el login: error legible, sin navegar', async () => {
    login.mockRejectedValue(new LeoApiError(500, 'internal_error', 'x'))
    await expect(middleware(route('/muestras'), route('/'))).rejects.toMatchObject({ statusCode: 503, statusMessage: expect.stringContaining('Inténtalo') })
    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('la página de retorno (pública) pasa sin sesión', async () => {
    expect(await middleware(route('/auth/callback?code=a&state=b', { public: true }), route('/'))).toBeUndefined()
    expect(login).not.toHaveBeenCalled()
  })

  it('con sesión: tags por permisos funcionan igual', async () => {
    useState('leo-session').value = {
      status: 'authenticated',
      me: {
        user: { id: 'u', username: 'a', email: '', first_name: 'A', last_name: '' },
        session: { id: 's', expires_at: '', last_activity_at: '', idle_timeout_seconds: 1800 },
        permissions: ['vladimir.samples.view'],
        applications: []
      }
    }
    expect(await middleware(route('/m', { tag: 'vladimir.samples.view' }), route('/'))).toBeUndefined()
    await middleware(route('/m', { tag: 'vladimir.samples.edit' }), route('/'))
    expect(navigateToMock).toHaveBeenCalledWith({ path: '/leo/forbidden', query: { from: '/m' } }, { replace: true })
  })
})
