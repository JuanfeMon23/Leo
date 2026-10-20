import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_USERS_TAGS, signInWith } from '../../../../tests/helpers/session'
import UsersDetail from './UsersDetail.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const apps = { items: [
  { id: 'a-leo', slug: 'leo', name: 'Leo', is_active: true },
  { id: 'a-tau', slug: 'taurus', name: 'Taurus', is_active: true }
], total: 2, page: 1, page_size: 200 }
const allRoles = { items: [
  { id: 'r1', application_id: 'a-leo', slug: 'adm', name: 'Administrador', is_active: true },
  { id: 'r2', application_id: 'a-tau', slug: 'caj', name: 'Cajero', is_active: true }
], total: 2, page: 1, page_size: 200 }
const roleWithActions = {
  id: 'r1', application_id: 'a-leo', slug: 'adm', name: 'Administrador', is_active: true,
  actions: [{ id: 'x1', tag: 'leo.users.view', name: 'Consultar usuarios', is_active: true }]
}
const detail = (over: Record<string, unknown> = {}, roles: unknown[] = [{ id: 'r1', application_id: 'a-leo', slug: 'adm', name: 'Administrador', is_active: true }]) => ({
  id: 'u2', username: 'luis', email: 'luis@x.co', document_type: 'CC', document_number: '99', first_name: 'Luis', last_name: 'Mora',
  is_active: true, last_login_at: null, failed_login_attempts: 0, locked_until: null, created_at: '', updated_at: '', roles, ...over
})

/** Enruta las llamadas de la API por método y ruta. */
function route(handlers: Record<string, unknown>) {
  api.mockImplementation(async (url: string, opts: { method?: string } = {}) => {
    const key = `${opts.method ?? 'GET'} ${url}`
    const h = handlers[key]
    if (h === undefined) throw new Error(`sin handler: ${key}`)
    if (h instanceof Error) throw h
    return h
  })
}
const base = (over: Record<string, unknown> = {}) => ({
  'GET /users/u2': detail(),
  'GET /applications': apps,
  'GET /roles': allRoles,
  'GET /roles/r1': roleWithActions,
  ...over
})

const byId = (id: string) => document.body.querySelector<HTMLElement>(`[data-testid="${id}"]`)

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_USERS_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

async function mountDetail(handlers: Record<string, unknown> = {}, id = 'u2') {
  route(base(handlers))
  const wrapper = await mountSuspended(UsersDetail, { props: { id }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('UsersDetail', () => {
  it('muestra datos, roles agrupados por aplicación y la línea «Acceso a»', async () => {
    const wrapper = await mountDetail({ 'GET /users/u2': detail({}, [
      { id: 'r1', application_id: 'a-leo', slug: 'adm', name: 'Administrador', is_active: true },
      { id: 'r2', application_id: 'a-tau', slug: 'caj', name: 'Cajero', is_active: false }
    ]), 'GET /roles/r2': { ...roleWithActions, id: 'r2', application_id: 'a-tau', is_active: false, actions: [] } })
    expect(wrapper.text()).toContain('Luis Mora')
    expect(wrapper.text()).toContain('luis@x.co')
    expect(wrapper.findAll('[data-testid="role-group"]').map(g => g.text())).toEqual([
      expect.stringContaining('Leo'), expect.stringContaining('Taurus')
    ])
    // Cajero está inactivo: no da acceso a Taurus.
    expect(wrapper.get('[data-testid="access-line"]').text()).toBe('Acceso a: Leo')
  })

  it('permisos efectivos con el nombre legible y el tag atenuado', async () => {
    const wrapper = await mountDetail()
    const perm = wrapper.get('[data-testid="effective-permission"]')
    expect(perm.text()).toContain('Consultar usuarios')
    expect(perm.get('code').text()).toBe('leo.users.view')
    expect(perm.get('code').classes()).toContain('text-text-muted')
  })

  it('asignar rol: el selector solo lista roles que no tiene, «Aplicación → Rol»', async () => {
    const wrapper = await mountDetail()
    const labels = [...wrapper.get('[data-testid="role-select"]').element.querySelectorAll('option')].map(o => o.textContent?.trim())
    expect(labels).toEqual(['Aplicación → Rol', 'Taurus → Cajero'])
  })

  it('quitar rol: confirma y llama a DELETE /users/{id}/roles/{role_id}', async () => {
    const wrapper = await mountDetail({ 'DELETE /users/u2/roles/r1': detail({}, []) })
    await wrapper.get('[data-testid="role-remove"]').trigger('click')
    await flushPromises()
    const confirm = [...document.body.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find(b => b.textContent?.trim() === 'Quitar rol')!
    confirm.click()
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/users/u2/roles/r1', { method: 'DELETE' })
    expect(wrapper.find('[data-testid="user-role"]').exists()).toBe(false)
  })

  it('desactivar: pide confirmación y llama a POST deactivate', async () => {
    const wrapper = await mountDetail({ 'POST /users/u2/deactivate': detail({ is_active: false }) })
    await wrapper.get('[data-testid="user-toggle"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('cerrarán todas sus sesiones')
    const confirm = [...document.body.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find(b => b.textContent?.trim() === 'Desactivar')!
    confirm.click()
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/users/u2/deactivate', { method: 'POST' })
  })

  it('un usuario no puede desactivarse a sí mismo: sin botón y con nota', async () => {
    // signInWith deja al usuario actual con id «u1».
    const wrapper = await mountDetail({ 'GET /users/u1': detail({ id: 'u1', username: 'ana' }) }, 'u1')
    expect(wrapper.find('[data-testid="user-toggle"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="self-note"]').text()).toContain('no puedes desactivarlo')
  })

  it('409 self_deactivation del backend: mensaje legible en el modal', async () => {
    const wrapper = await mountDetail({ 'POST /users/u2/deactivate': new LeoApiError(409, 'self_deactivation', 'No puedes desactivar tu propio usuario.') })
    await wrapper.get('[data-testid="user-toggle"]').trigger('click')
    await flushPromises()
    const confirm = [...document.body.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find(b => b.textContent?.trim() === 'Desactivar')!
    confirm.click()
    await flushPromises()
    expect(document.body.textContent).toContain('No puedes desactivar tu propio usuario')
    expect(document.body.textContent).not.toMatch(/self_deactivation/)
  })

  it('desbloquear solo aparece si el usuario está bloqueado', async () => {
    let wrapper = await mountDetail()
    expect(wrapper.find('[data-testid="user-unlock"]').exists()).toBe(false)
    wrapper.unmount()
    wrapper = await mountDetail({ 'GET /users/u2': detail({ locked_until: new Date(Date.now() + 600_000).toISOString() }) })
    expect(wrapper.find('[data-testid="user-unlock"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="user-status"]').attributes('data-status')).toBe('locked')
  })

  it('sin tags de acción: no hay Editar, Restablecer, Desactivar ni asignar/quitar roles', async () => {
    signInWith(['leo.users.view'])
    const wrapper = await mountDetail()
    for (const id of ['user-edit', 'user-reset', 'user-toggle', 'user-unlock', 'role-remove', 'role-assigner']) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(false)
    }
  })

  it('error al cargar: mensaje legible', async () => {
    api.mockReset()
    api.mockRejectedValue(new LeoApiError(404, 'not_found', "No existe un usuario con id 'u2'."))
    const wrapper = await mountSuspended(UsersDetail, { props: { id: 'u2' }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.get('[data-testid="detail-error"]').text()).toContain('No existe un usuario')
    expect(byId('user-toggle')).toBeNull()
  })
})
