import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_APPLICATIONS_TAGS, signInWith } from '../../../../tests/helpers/session'
import ApplicationsList from './ApplicationsList.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const app = (over: Record<string, unknown> = {}) => ({
  id: 'a1', slug: 'vladimir', name: 'Vladimir', description: null, base_url: 'https://v.test',
  redirect_uris: [], client_id: 'vladimir', is_active: true, created_at: '', updated_at: '', ...over
})
const page = (items: unknown[], total = items.length) => ({ items, total, page: 1, page_size: 20 })

const byId = (id: string) => document.body.querySelector<HTMLElement>(`[data-testid="${id}"]`)

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_APPLICATIONS_TAGS)
})

afterEach(() => {
  document.body.innerHTML = ''
})

async function mountList() {
  const wrapper = await mountSuspended(ApplicationsList, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('ApplicationsList', () => {
  it('carga la primera página y muestra las aplicaciones', async () => {
    api.mockResolvedValue(page([app(), app({ id: 'a2', slug: 'incubus', name: 'Incubus', is_active: false })]))
    const wrapper = await mountList()
    expect(api).toHaveBeenCalledWith('/applications', { query: { page: 1, page_size: 20 } })
    expect(wrapper.text()).toContain('Vladimir')
    expect(wrapper.text()).toContain('Incubus')
    expect(wrapper.text()).toContain('Activo')
    expect(wrapper.text()).toContain('Inactivo')
  })

  it('sin resultados: mensaje de vacío', async () => {
    api.mockResolvedValue(page([]))
    const wrapper = await mountList()
    expect(wrapper.text()).toContain('Aún no hay aplicaciones registradas.')
  })

  it('error de carga: mensaje legible, no el crudo', async () => {
    api.mockRejectedValue(new TypeError('Failed to fetch'))
    const wrapper = await mountList()
    const text = wrapper.get('[data-testid="apps-error"]').text()
    expect(text).toContain('No se pudo conectar')
    expect(text).not.toMatch(/fetch/i)
  })

  it('con todos los tags muestra crear, editar, rotar y desactivar', async () => {
    api.mockResolvedValue(page([app()]))
    const wrapper = await mountList()
    for (const id of ['app-create', 'app-edit', 'app-rotate', 'app-toggle']) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), id).toBe(true)
    }
  })

  it('solo con view: sin ningún botón de escritura', async () => {
    signInWith(['leo.applications.view'])
    api.mockResolvedValue(page([app()]))
    const wrapper = await mountList()
    for (const id of ['app-create', 'app-edit', 'app-rotate', 'app-toggle']) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), id).toBe(false)
    }
    expect(wrapper.text()).toContain('Ver')
  })

  it('cada tag controla su botón', async () => {
    signInWith(['leo.applications.view', 'leo.applications.rotate-secret'])
    api.mockResolvedValue(page([app()]))
    const wrapper = await mountList()
    expect(wrapper.find('[data-testid="app-rotate"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="app-edit"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="app-toggle"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="app-create"]').exists()).toBe(false)
  })

  it('la app leo (protegida) se muestra sin controles de escritura', async () => {
    api.mockResolvedValue(page([app({ id: 'l', slug: 'leo', name: 'Leo', client_id: 'leo' })]))
    const wrapper = await mountList()
    expect(wrapper.text()).toContain('Leo')
    for (const id of ['app-edit', 'app-rotate', 'app-toggle']) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), id).toBe(false)
    }
  })

  it('desactivar pide confirmación y solo entonces llama a la API', async () => {
    api.mockResolvedValue(page([app()]))
    const wrapper = await mountList()
    await wrapper.get('[data-testid="app-toggle"]').trigger('click')
    expect(document.body.textContent).toContain('Se desactivará «Vladimir»')
    expect(api).not.toHaveBeenCalledWith('/applications/a1/deactivate', expect.anything())

    api.mockImplementation(async (path: string) => (path === '/applications' ? page([app({ is_active: false })]) : app({ is_active: false })))
    const confirm = [...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Desactivar' && b.closest('[role="dialog"]'))!
    confirm.click()
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/applications/a1/deactivate', { method: 'POST' })
  })

  it('error al desactivar: se queda en el modal con un mensaje legible', async () => {
    api.mockResolvedValue(page([app()]))
    const wrapper = await mountList()
    await wrapper.get('[data-testid="app-toggle"]').trigger('click')
    api.mockImplementation(async (path: string) => {
      if (path === '/applications') return page([app()])
      throw new LeoApiError(409, 'leo_app_protected', 'texto')
    })
    const confirm = [...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Desactivar' && b.closest('[role="dialog"]'))!
    confirm.click()
    await flushPromises()
    expect(document.body.querySelector('[role="dialog"]')!.textContent).toContain('no se puede modificar')
  })

  it('rotar secreto: confirma y muestra el secreto nuevo una sola vez', async () => {
    api.mockResolvedValue(page([app()]))
    const wrapper = await mountList()
    await wrapper.get('[data-testid="app-rotate"]').trigger('click')
    api.mockImplementation(async (path: string) => (path === '/applications' ? page([app()]) : { client_id: 'vladimir', client_secret: 'NUEVO-SECRETO' }))
    const confirm = [...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Rotar secreto' && b.closest('[role="dialog"]'))!
    confirm.click()
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/applications/a1/rotate-secret', { method: 'POST' })
    expect(byId('secret-value')!.textContent).toBe('NUEVO-SECRETO')

    byId('secret-done')!.click()
    await flushPromises()
    expect(byId('secret-value')).toBeNull()
    expect(document.body.textContent).not.toContain('NUEVO-SECRETO')
  })
})
