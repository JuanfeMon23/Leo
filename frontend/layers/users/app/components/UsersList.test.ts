import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ALL_USERS_TAGS, signInWith } from '../../../../tests/helpers/session'
import UsersList from './UsersList.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const future = new Date(Date.now() + 15 * 60_000)
const user = (over: Record<string, unknown> = {}) => ({
  id: 'u1', username: 'ana', email: 'ana@x.co', document_type: 'CC', document_number: '123', first_name: 'Ana', last_name: 'Pérez',
  is_active: true, last_login_at: null, failed_login_attempts: 0, locked_until: null, created_at: '', updated_at: '', ...over
})
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 20 })

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_USERS_TAGS)
  api.mockResolvedValue(page([
    user(),
    user({ id: 'u2', username: 'luis', first_name: 'Luis', last_name: 'Mora', is_active: false }),
    user({ id: 'u3', username: 'eva', first_name: 'Eva', last_name: 'Ríos', locked_until: future.toISOString(), last_login_at: new Date(2026, 0, 5, 7, 9).toISOString() })
  ]))
})
afterEach(() => { document.body.innerHTML = '' })

async function mountList() {
  const wrapper = await mountSuspended(UsersList, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('UsersList', () => {
  it('pide la primera página y muestra nombre completo, usuario, correo y documento', async () => {
    const wrapper = await mountList()
    expect(api).toHaveBeenCalledWith('/users', { query: { page: 1, page_size: 20 } })
    const text = wrapper.text()
    expect(text).toContain('Ana Pérez')
    expect(text).toContain('ana@x.co')
    expect(text).toContain('CC 123')
  })

  it('estado: activo, inactivo y bloqueado hasta HH:MM; último acceso o «Nunca»', async () => {
    const wrapper = await mountList()
    const statuses = wrapper.findAll('[data-testid="user-status"]').map(s => s.attributes('data-status'))
    expect(statuses).toEqual(['active', 'inactive', 'locked'])
    expect(wrapper.text()).toMatch(/Bloqueado hasta \d{2}:\d{2}/)
    expect(wrapper.text()).toContain('Nunca')
    expect(wrapper.text()).toContain('05/01/2026 07:09')
  })

  it('el filtro de inactivos vuelve a consultar con active=false', async () => {
    const wrapper = await mountList()
    await wrapper.get('select#ui-active-filter').setValue('inactive')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/users', { query: { page: 1, page_size: 20, active: false } })
  })

  it('error de carga: mensaje legible, no el crudo', async () => {
    api.mockReset()
    api.mockRejectedValue(new TypeError('Failed to fetch'))
    const wrapper = await mountList()
    const text = wrapper.get('[data-testid="users-error"]').text()
    expect(text).toContain('No se pudo conectar')
    expect(text).not.toMatch(/fetch/i)
  })

  it('con todos los tags: Nuevo usuario, Ver y Editar; solo con view: nada de eso salvo Ver', async () => {
    let wrapper = await mountList()
    expect(wrapper.find('[data-testid="user-create"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid="user-edit"]')).toHaveLength(3)
    wrapper.unmount()
    signInWith(['leo.users.view'])
    wrapper = await mountList()
    expect(wrapper.find('[data-testid="user-create"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="user-edit"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="user-view"]')).toHaveLength(3)
  })
})
