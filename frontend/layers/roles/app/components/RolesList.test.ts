import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ALL_ROLES_TAGS, signInWith } from '../../../../tests/helpers/session'
import RolesList from './RolesList.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const role = (over: Record<string, unknown> = {}) => ({
  id: 'r1', application_id: 'app1', slug: 'analista', name: 'Analista', description: null, is_active: true, created_at: '', updated_at: '', ...over
})
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 20 })
const apps = page([
  { id: 'app1', slug: 'vladimir', name: 'Vladimir', is_active: true },
  { id: 'app2', slug: 'incubus', name: 'Incubus', is_active: true }
])

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_ROLES_TAGS)
  api.mockImplementation(async (url: string) => (url === '/applications' ? apps : page([role(), role({ id: 'r2', slug: 'revisor', name: 'Revisor', is_active: false, application_id: 'app2' })])))
})
afterEach(() => { document.body.innerHTML = '' })

async function mountList() {
  const wrapper = await mountSuspended(RolesList, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('RolesList', () => {
  it('lista roles con el nombre de su aplicación y estado', async () => {
    const wrapper = await mountList()
    expect(api).toHaveBeenCalledWith('/roles', { query: { page: 1, page_size: 20 } })
    const text = wrapper.text()
    expect(text).toContain('Analista')
    expect(text).toContain('Vladimir')
    expect(text).toContain('Incubus')
    expect(text).toContain('Inactivo')
  })

  it('el filtro por aplicación vuelve a consultar con application_id', async () => {
    const wrapper = await mountList()
    await wrapper.get('[data-testid="app-filter"] select, select[data-testid="app-filter"]').setValue('app2')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/roles', { query: { page: 1, page_size: 20, application_id: 'app2' } })
  })

  it('error de carga: mensaje legible, no el crudo', async () => {
    api.mockReset()
    api.mockRejectedValue(new TypeError('Failed to fetch'))
    const wrapper = await mountList()
    const text = wrapper.get('[data-testid="roles-error"]').text()
    expect(text).toContain('No se pudo conectar')
    expect(text).not.toMatch(/fetch/i)
  })

  it('si no se pueden leer las aplicaciones, el listado funciona y se avisa', async () => {
    api.mockImplementation(async (url: string) => {
      if (url === '/applications') throw new TypeError('Failed to fetch')
      return page([role()])
    })
    const wrapper = await mountList()
    expect(wrapper.text()).toContain('Analista')
    expect(wrapper.get('[data-testid="apps-error"]').text()).toContain('No se pudo cargar la lista de aplicaciones')
  })

  it('con todos los tags: crear, editar, permisos y activar/desactivar', async () => {
    const wrapper = await mountList()
    for (const id of ['role-create', 'role-edit', 'role-toggle', 'role-view']) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), id).toBe(true)
    }
  })

  it('solo con view: nada de escritura, pero sí ver permisos', async () => {
    signInWith(['leo.roles.view'])
    const wrapper = await mountList()
    for (const id of ['role-create', 'role-edit', 'role-toggle']) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), id).toBe(false)
    }
    expect(wrapper.find('[data-testid="role-view"]').exists()).toBe(true)
  })

  it('desactivar pide confirmación y llama a la API', async () => {
    const wrapper = await mountList()
    await wrapper.get('[data-testid="role-toggle"]').trigger('click')
    expect(document.body.textContent).toContain('Se desactivará «Analista»')
    const confirm = [...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Desactivar' && b.closest('[role="dialog"]'))!
    confirm.click()
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/roles/r1/deactivate', { method: 'POST' })
  })
})
