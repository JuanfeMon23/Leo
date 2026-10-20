import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ALL_APPLICATIONS_TAGS, signInWith } from '../../../../tests/helpers/session'
import ApplicationsDetail from './ApplicationsDetail.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

function detail(slug = 'vladimir') {
  return {
    id: 'a1', slug, name: slug === 'leo' ? 'Leo' : 'Vladimir', description: 'Muestras', base_url: 'https://v.test',
    redirect_uris: ['https://v.test/cb'], client_id: slug, is_active: true, created_at: '', updated_at: '',
    modules: [{
      id: 'm1', application_id: 'a1', slug: 'samples', name: 'Muestras', description: null, is_active: true,
      actions: [
        { id: 'x1', module_id: 'm1', verb: 'view', tag: `${slug}.samples.view`, name: 'Consultar muestras', description: 'Ver muestras', is_active: true },
        { id: 'x2', module_id: 'm1', verb: 'login', tag: `${slug}.samples.login`, name: 'Inicio de sesión', description: 'Evento: inicio de sesion', is_active: true }
      ]
    }]
  }
}

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_APPLICATIONS_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

async function mountDetail(slug?: string) {
  api.mockImplementation(async (url: string) => (url.endsWith('/service-access') ? [] : detail(slug)))
  const wrapper = await mountSuspended(ApplicationsDetail, { props: { id: 'a1' }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('ApplicationsDetail', () => {
  it('muestra datos, módulos y acciones con su tag', async () => {
    const wrapper = await mountDetail()
    expect(api).toHaveBeenCalledWith('/applications/a1')
    const text = wrapper.text()
    expect(text).toContain('Vladimir')
    expect(text).toContain('https://v.test/cb')
    expect(text).toContain('Muestras')
    expect(text).toContain('vladimir.samples.view')
  })

  it('cada acción muestra su nombre legible como principal y el tag como referencia pequeña', async () => {
    const wrapper = await mountDetail()
    const row = wrapper.findAll('[data-testid="action-row"]')[0]!
    expect(row.get('[data-testid="action-name"]').text()).toBe('Consultar muestras')
    const tag = row.get('[data-testid="action-tag"]')
    expect(tag.text()).toBe('vladimir.samples.view')
    expect(tag.classes()).toContain('text-xs')
  })

  it('la acción de evento lleva insignia «Evento» y no tiene controles; la normal sí', async () => {
    const wrapper = await mountDetail()
    const rows = wrapper.findAll('[data-testid="action-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.find('[data-testid="event-badge"]').exists()).toBe(false)
    expect(rows[0]!.find('[data-testid="action-edit"]').exists()).toBe(true)
    expect(rows[0]!.find('[data-testid="action-toggle"]').exists()).toBe(true)
    expect(rows[1]!.find('[data-testid="event-badge"]').text()).toBe('Evento')
    expect(rows[1]!.find('[data-testid="action-edit"]').exists()).toBe(false)
    expect(rows[1]!.find('[data-testid="action-toggle"]').exists()).toBe(false)
  })

  it('la app leo es de solo lectura: aviso y ningún control de escritura', async () => {
    const wrapper = await mountDetail('leo')
    expect(wrapper.find('[data-testid="readonly-notice"]').exists()).toBe(true)
    for (const id of ['app-edit', 'app-rotate', 'app-toggle', 'module-create', 'module-edit', 'module-toggle', 'action-create', 'action-edit', 'action-toggle']) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), id).toBe(false)
    }
  })

  it('con todos los tags una app normal muestra los controles', async () => {
    const wrapper = await mountDetail()
    expect(wrapper.find('[data-testid="readonly-notice"]').exists()).toBe(false)
    for (const id of ['app-edit', 'app-rotate', 'app-toggle', 'module-create', 'module-edit', 'module-toggle', 'action-create']) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), id).toBe(true)
    }
  })

  it('solo con view: nada de escritura', async () => {
    signInWith(['leo.applications.view'])
    const wrapper = await mountDetail()
    for (const id of ['app-edit', 'app-rotate', 'app-toggle', 'module-create', 'module-edit', 'module-toggle', 'action-create', 'action-edit', 'action-toggle']) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), id).toBe(false)
    }
  })

  it('error de carga (404): mensaje legible del backend', async () => {
    const { LeoApiError } = await import('#leo-client/lib/errors')
    api.mockRejectedValue(new LeoApiError(404, 'not_found', 'No se encontró la aplicación.'))
    const wrapper = await mountSuspended(ApplicationsDetail, { props: { id: 'zzz' }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.get('[data-testid="detail-error"]').text()).toContain('No se encontró la aplicación.')
  })

  it('desactivar un módulo pide confirmación y llama a la API', async () => {
    const wrapper = await mountDetail()
    await wrapper.get('[data-testid="module-toggle"]').trigger('click')
    expect(document.body.textContent).toContain('Se desactivará el módulo «Muestras»')
    api.mockResolvedValue(detail())
    const confirm = [...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Desactivar' && b.closest('[role="dialog"]'))!
    confirm.click()
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/applications/a1/modules/m1/deactivate', { method: 'POST' })
  })
})
