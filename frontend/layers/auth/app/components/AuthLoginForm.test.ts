import { flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import AuthLoginForm from './AuthLoginForm.vue'

enableAutoUnmount(afterEach)

const { api, navigate } = vi.hoisted(() => ({ api: vi.fn(), navigate: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)
mockNuxtImport('navigateTo', () => navigate)

const ME = {
  user: { id: 'u1', username: 'ana', email: 'ana@x.co', first_name: 'Ana', last_name: 'Pérez' },
  session: { id: 's1', expires_at: '', last_activity_at: '', idle_timeout_seconds: 0 },
  permissions: [],
  applications: []
}

beforeEach(() => {
  api.mockReset()
  navigate.mockReset()
  useState('leo-session').value = { status: 'anonymous', me: null }
})

async function fill(wrapper: Awaited<ReturnType<typeof mountSuspended>>, login: string, password: string) {
  const inputs = wrapper.findAll('input')
  await inputs[0]!.setValue(login)
  await inputs[1]!.setValue(password)
  await wrapper.get('form').trigger('submit')
  // La validación de vee-validate es asíncrona: esperar a que llegue a la API y termine.
  await vi.waitFor(() => expect(api).toHaveBeenCalled())
  await vi.waitFor(() => expect(wrapper.find('button[aria-busy="true"]').exists()).toBe(false))
  await flushPromises()
}

describe('AuthLoginForm', () => {
  it('campos vacíos: errores de validación y no llama a la API', async () => {
    const wrapper = await mountSuspended(AuthLoginForm)
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Ingresa tu usuario o correo electrónico.'))
    expect(wrapper.text()).toContain('Ingresa tu contraseña.')
    expect(api).not.toHaveBeenCalled()
  })

  it('login correcto: guarda la sesión y vuelve al destino interno', async () => {
    api.mockResolvedValue(ME)
    const wrapper = await mountSuspended(AuthLoginForm, { props: { redirect: '/authorize?client_id=x' } })
    await fill(wrapper, ' ana ', 'secreto')
    expect(api).toHaveBeenCalledWith('/auth/login', { method: 'POST', body: { login: 'ana', password: 'secreto' }, skipSessionHandling: true })
    expect(useState<{ status: string }>('leo-session').value.status).toBe('authenticated')
    expect(navigate).toHaveBeenCalledWith('/authorize?client_id=x', { replace: true })
  })

  it('redirect externo se ignora y va al inicio', async () => {
    api.mockResolvedValue(ME)
    const wrapper = await mountSuspended(AuthLoginForm, { props: { redirect: 'https://evil.example/x' } })
    await fill(wrapper, 'ana', 'secreto')
    expect(navigate).toHaveBeenCalledWith('/', { replace: true })
  })

  it('credenciales inválidas: muestra el mensaje y no navega', async () => {
    api.mockRejectedValue(new LeoApiError(401, 'invalid_credentials', 'Usuario o contraseña incorrectos.'))
    const wrapper = await mountSuspended(AuthLoginForm)
    await fill(wrapper, 'ana', 'mala')
    expect(wrapper.get('[data-testid="login-error"]').text()).toContain('Usuario o contraseña incorrectos.')
    expect(navigate).not.toHaveBeenCalled()
  })

  it('bloqueo 429: muestra el tiempo restante', async () => {
    api.mockRejectedValue(new LeoApiError(429, 'too_many_attempts', 'x', null, 300))
    const wrapper = await mountSuspended(AuthLoginForm)
    await fill(wrapper, 'ana', 'mala')
    expect(wrapper.get('[data-testid="login-error"]').text()).toContain('en 5 minutos')
  })

  it('error de red: mensaje legible, no el crudo', async () => {
    api.mockRejectedValue(new TypeError('Failed to fetch'))
    const wrapper = await mountSuspended(AuthLoginForm)
    await fill(wrapper, 'ana', 'x')
    const text = wrapper.get('[data-testid="login-error"]').text()
    expect(text).not.toMatch(/fetch/i)
    expect(text).toContain('No se pudo conectar')
  })

  it('?reason=idle explica por qué se cerró la sesión', async () => {
    const wrapper = await mountSuspended(AuthLoginForm, { props: { reason: 'idle' } })
    expect(wrapper.get('[data-testid="login-reason"]').text()).toContain('inactividad')
  })

  it('sin reason conocido no muestra aviso', async () => {
    const wrapper = await mountSuspended(AuthLoginForm, { props: { reason: 'otro' } })
    expect(wrapper.find('[data-testid="login-reason"]').exists()).toBe(false)
  })
})
