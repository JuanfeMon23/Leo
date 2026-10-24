import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import type { VueWrapper } from '@vue/test-utils'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_SESSIONS_TAGS, signInWith } from '../../../../tests/helpers/session'
import SessionsList from './SessionsList.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const future = (min: number) => new Date(Date.now() + min * 60_000).toISOString()
const past = (min: number) => new Date(Date.now() - min * 60_000).toISOString()
const CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
const session = (over: Record<string, unknown> = {}) => ({
  id: 's1', user_id: 'u1', ip: '10.0.0.7', user_agent: CHROME, created_at: new Date(2026, 9, 19, 8, 0).toISOString(),
  last_activity_at: new Date(2026, 9, 19, 9, 41).toISOString(), expires_at: future(20), revoked_at: null, revoked_reason: null, is_current: false, ...over
})
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 20 })
const users = { items: [{ id: 'u1', username: 'ana', first_name: 'Ana', last_name: 'Pérez' }, { id: 'u2', username: 'luis', first_name: 'Luis', last_name: 'Mora' }], total: 2, page: 1, page_size: 200 }

let sessions: unknown[]
function route(over: Record<string, unknown> = {}) {
  const handlers: Record<string, unknown> = { 'GET /auth/sessions': () => page(sessions), 'GET /users': users, ...over }
  api.mockImplementation(async (url: string, opts: { method?: string } = {}) => {
    const key = `${opts.method ?? 'GET'} ${url.replace(/\/[^/]+\/revoke$/, '/{id}/revoke')}`
    const h = handlers[key]
    if (h === undefined) throw new Error(`sin handler: ${key}`)
    if (h instanceof Error) throw h
    return typeof h === 'function' ? h() : h
  })
}
/** Filas del cuerpo de la tabla (sin la cabecera). */
const bodyRows = (w: VueWrapper) => w.findAll('tr').slice(1)
const sessionCalls = () => api.mock.calls.filter(c => c[0] === '/auth/sessions')

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_SESSIONS_TAGS)
  sessions = [
    session({ is_current: true }),
    session({ id: 's2', user_id: 'u2', expires_at: past(5) }),
    session({ id: 's3', revoked_at: past(60), revoked_reason: 'admin', ip: null, user_agent: null })
  ]
  route()
})
afterEach(() => { document.body.innerHTML = '' })

async function mountList() {
  const wrapper = await mountSuspended(SessionsList, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('SessionsList', () => {
  it('por defecto pide las propias y solo activas', async () => {
    await mountList()
    expect(api).toHaveBeenCalledWith('/auth/sessions', { query: { page: 1, page_size: 20, active_only: true } })
  })

  it('muestra dueño, fechas locales, IP y navegador resumido', async () => {
    const wrapper = await mountList()
    const row = bodyRows(wrapper)[0]!
    expect(row.get('[data-testid="session-owner"]').text()).toBe('Ana Pérez')
    expect(row.text()).toContain('19/10/2026 08:00')
    expect(row.text()).toContain('19/10/2026 09:41')
    expect(row.get('[data-testid="session-ip"]').text()).toBe('10.0.0.7')
    expect(row.get('[data-testid="session-agent"]').text()).toBe('Chrome 141 en Windows')
  })

  it('estados: Activa, Inactiva por tiempo y Revocada con su motivo', async () => {
    const wrapper = await mountList()
    const statuses = wrapper.findAll('[data-testid="session-status"]')
    expect(statuses.map(s => s.attributes('data-status'))).toEqual(['active', 'idle', 'revoked'])
    expect(statuses[0]!.text()).toBe('Activa')
    expect(statuses[1]!.text()).toBe('Inactiva por tiempo')
    expect(statuses[2]!.text()).toContain('Revocada')
    expect(statuses[2]!.get('[data-testid="session-reason"]').text()).toBe('Revocada por un administrador')
  })

  it('marca «Esta sesión» solo en la actual', async () => {
    const wrapper = await mountList()
    expect(wrapper.findAll('[data-testid="session-current"]')).toHaveLength(1)
    expect(bodyRows(wrapper)[0]!.find('[data-testid="session-current"]').exists()).toBe(true)
  })

  it('solo las sesiones activas ofrecen revocar', async () => {
    const wrapper = await mountList()
    expect(wrapper.findAll('[data-testid="session-revoke"]')).toHaveLength(1)
  })

  it('sin leo.auth.revoke no hay botón de revocar', async () => {
    signInWith(['leo.auth.view'])
    const wrapper = await mountList()
    expect(wrapper.find('[data-testid="session-revoke"]').exists()).toBe(false)
    expect(wrapper.findAll('th').some(th => th.text() === 'Acciones')).toBe(false)
  })

  it('con leo.auth.revoke la columna «Acciones» existe', async () => {
    const wrapper = await mountList()
    expect(wrapper.findAll('th').some(th => th.text() === 'Acciones')).toBe(true)
  })

  it('filtrar por usuario pide sus sesiones; «solo activas» desmarcado envía active_only=false', async () => {
    const wrapper = await mountList()
    await wrapper.get('[data-testid="session-user-filter"]').setValue('u2')
    await flushPromises()
    expect(sessionCalls().at(-1)![1]).toEqual({ query: { page: 1, page_size: 20, active_only: true, user_id: 'u2' } })
    await wrapper.get('[data-testid="session-active-only"] input').setValue(false)
    await flushPromises()
    expect(sessionCalls().at(-1)![1]).toEqual({ query: { page: 1, page_size: 20, active_only: false, user_id: 'u2' } })
  })

  it('revocar otra sesión: pide confirmación, llama al POST y recarga', async () => {
    sessions = [session({ id: 's9', user_id: 'u2' })]
    api.mockImplementation(async (url: string, opts: { method?: string } = {}) => {
      if (opts.method === 'POST') return undefined
      if (url === '/users') return users
      return page(sessions)
    })
    const wrapper = await mountList()
    await wrapper.get('[data-testid="session-revoke"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('Revocar sesión')
    expect(document.body.textContent).not.toContain('se cerrará tu sesión')
    const confirmButton = [...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Revocar' && b.closest('[role="dialog"]'))!
    confirmButton.click()
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/auth/sessions/s9/revoke', { method: 'POST' })
    expect(sessionCalls().length).toBeGreaterThanOrEqual(2)
  })

  it('revocar la propia sesión advierte que cerrará la sesión de quien confirma', async () => {
    const wrapper = await mountList()
    await wrapper.get('[data-testid="session-revoke"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('se cerrará tu sesión')
    expect(document.body.textContent).toContain('Cerrar mi sesión')
  })

  it('si revocar falla, el modal muestra el mensaje legible y no llama a recargar', async () => {
    route({ 'POST /auth/sessions/{id}/revoke': new LeoApiError(404, 'not_found', 'No se encontró la sesión.') })
    const wrapper = await mountList()
    const before = sessionCalls().length
    await wrapper.get('[data-testid="session-revoke"]').trigger('click')
    await flushPromises()
    const confirmButton = [...document.body.querySelectorAll('button')].find(b => b.textContent?.includes('Cerrar mi sesión'))!
    confirmButton.click()
    await flushPromises()
    expect(document.body.textContent).toContain('No se encontró la sesión.')
    expect(sessionCalls()).toHaveLength(before)
  })

  it('error del listado: mensaje legible', async () => {
    route({ 'GET /auth/sessions': new LeoApiError(403, 'forbidden', 'No tienes permiso para ver sesiones.') })
    const wrapper = await mountList()
    expect(wrapper.get('[data-testid="sessions-error"]').text()).toContain('No tienes permiso para ver sesiones.')
  })

  it('sin acceso a /users avisa y muestra «Usuario desconocido»', async () => {
    route({ 'GET /users': new LeoApiError(403, 'forbidden', 'No tienes permiso.') })
    const wrapper = await mountList()
    expect(wrapper.find('[data-testid="sessions-users-error"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="session-owner"]').text()).toBe('Usuario desconocido')
  })
})
