import { flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import AuthAuthorizePanel from './AuthAuthorizePanel.vue'

enableAutoUnmount(afterEach)

const { api, navigate } = vi.hoisted(() => ({ api: vi.fn(), navigate: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)
mockNuxtImport('navigateTo', () => navigate)

const query = {
  client_id: 'vladimir',
  redirect_uri: 'http://localhost:3200/cb',
  state: 's',
  code_challenge: 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM',
  code_challenge_method: 'S256',
  dpop_jkt: 'NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs'
}
const fullPath = '/authorize?client_id=vladimir'

function authenticate() {
  useState('leo-session').value = {
    status: 'authenticated',
    me: {
      user: { id: 'u1', username: 'ana', email: 'a@x.co', first_name: 'Ana', last_name: 'P' },
      session: { id: 's', expires_at: '', last_activity_at: '', idle_timeout_seconds: 0 },
      permissions: [],
      applications: []
    }
  }
}

beforeEach(() => {
  api.mockReset()
  navigate.mockReset()
  authenticate()
})

describe('AuthAuthorizePanel', () => {
  it('faltan parámetros: error legible y no llama a la API', async () => {
    const wrapper = await mountSuspended(AuthAuthorizePanel, { props: { query: { client_id: 'x' }, fullPath } })
    await flushPromises()
    expect(wrapper.get('[data-testid="authorize-error"]').text()).toContain('redirect_uri')
    expect(api).not.toHaveBeenCalled()
  })

  it('sin sesión: va a /login con la URL completa de authorize para volver', async () => {
    useState('leo-session').value = { status: 'anonymous', me: null }
    await mountSuspended(AuthAuthorizePanel, { props: { query, fullPath } })
    await flushPromises()
    expect(navigate).toHaveBeenCalledWith('/login?redirect=%2Fauthorize%3Fclient_id%3Dvladimir', { external: false, replace: true })
    expect(api).not.toHaveBeenCalled()
  })

  it('403 access_denied: "No tienes acceso a <app>" y enlace para volver', async () => {
    api.mockRejectedValue(new LeoApiError(403, 'access_denied', 'x'))
    const wrapper = await mountSuspended(AuthAuthorizePanel, { props: { query, fullPath } })
    await flushPromises()
    const box = wrapper.get('[data-testid="authorize-forbidden"]')
    expect(box.text()).toContain('No tienes acceso a «vladimir».')
    expect(box.get('a').attributes('href')).toBe('/')
  })

  it('error de red: mensaje legible con opción de reintentar', async () => {
    api.mockRejectedValue(new TypeError('Failed to fetch'))
    const wrapper = await mountSuspended(AuthAuthorizePanel, { props: { query, fullPath } })
    await flushPromises()
    const text = wrapper.get('[data-testid="authorize-error"]').text()
    expect(text).not.toMatch(/fetch/i)
    expect(text).toContain('Reintentar')
  })

  it('401 con sesión vencida: limpia la sesión y va al login', async () => {
    api.mockRejectedValue(new LeoApiError(401, 'session_expired', 'Tu sesión expiró.'))
    await mountSuspended(AuthAuthorizePanel, { props: { query, fullPath } })
    await flushPromises()
    expect(useState<{ status: string }>('leo-session').value.status).toBe('anonymous')
    expect(navigate).toHaveBeenCalledWith(expect.stringContaining('/login?redirect='), expect.anything())
  })
})
