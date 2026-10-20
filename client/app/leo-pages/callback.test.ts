import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Callback from './callback.vue'
import { LeoApiError } from '../lib/errors'
import type { LeoMe } from '../lib/types'

enableAutoUnmount(afterEach)

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn(async (to: unknown) => to) }))
mockNuxtImport('navigateTo', () => navigateToMock)

const ME: LeoMe = {
  user: { id: 'u1', username: 'ana', email: 'a@x.co', first_name: 'Ana', last_name: '' },
  session: { id: 's', expires_at: '', last_activity_at: '', idle_timeout_seconds: 1800 },
  permissions: ['vladimir.samples.view'],
  applications: []
}

const completeLogin = vi.fn()
const login = vi.fn()

beforeEach(() => {
  navigateToMock.mockClear()
  completeLogin.mockReset()
  login.mockReset()
  useState('leo-session').value = { status: 'unknown', me: null }
  Object.assign(useNuxtApp().$leo.transport, { kind: 'bff', completeLogin, login })
})

const mountAt = (query: string) => mountSuspended(Callback, { route: `/auth/callback${query}` })
const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('página de retorno de login (bff)', () => {
  it('canjea code+state, fija la sesión y vuelve a la ruta de origen', async () => {
    completeLogin.mockResolvedValue({ me: ME, returnTo: '/muestras?page=2' })
    await mountAt('?code=c1&state=s1')
    await flush()
    expect(completeLogin).toHaveBeenCalledWith({ code: 'c1', state: 's1' })
    expect(useState<{ status: string }>('leo-session').value.status).toBe('authenticated')
    expect(navigateToMock).toHaveBeenCalledWith('/muestras?page=2', { replace: true })
  })

  it('error del backend: mensaje legible (sin respuesta cruda) y reintento', async () => {
    completeLogin.mockRejectedValue(new LeoApiError(400, 'invalid_state', 'La solicitud de inicio de sesión expiró o no es válida.'))
    login.mockResolvedValue({ url: 'http://leo.test/authorize?x=1', external: true })
    const wrapper = await mountAt('?code=c1&state=s1')
    await flush()
    expect(wrapper.get('[data-testid="leo-callback-error"]').text()).toBe('La solicitud de inicio de sesión expiró o no es válida.')
    expect(navigateToMock).not.toHaveBeenCalled()

    await wrapper.get('button').trigger('click')
    await flush()
    expect(login).toHaveBeenCalled()
    expect(navigateToMock).toHaveBeenCalledWith('http://leo.test/authorize?x=1', { external: true, replace: true })
  })

  it('?error de Leo o sin code/state: no llama al backend y muestra mensaje', async () => {
    for (const query of ['?error=access_denied', '?code=c1', '']) {
      const wrapper = await mountAt(query)
      await flush()
      expect(wrapper.find('[data-testid="leo-callback-error"]').exists()).toBe(true)
    }
    expect(completeLogin).not.toHaveBeenCalled()
  })
})

describe('registro de la ruta', () => {
  it('la capa registra la página en callbackPath (configurable) y es pública', () => {
    const path = useRuntimeConfig().public.leo.callbackPath
    expect(path).toBe('/auth/callback')
    const resolved = useRouter().resolve(path)
    expect(resolved.name).toBe('leo-callback')
    expect(resolved.meta.leo).toEqual({ public: true })
  })
})
