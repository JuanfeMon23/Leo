import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import type { VueWrapper } from '@vue/test-utils'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_AUDIT_TAGS, signInWith } from '../../../../tests/helpers/session'
import AuditList from './AuditList.vue'

enableAutoUnmount(afterEach)

const { api, download } = vi.hoisted(() => ({ api: vi.fn(), download: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)
mockNuxtImport('downloadBlob', () => download)

const event = (over: Record<string, unknown> = {}) => ({
  id: 'e1', occurred_at: new Date(2026, 9, 19, 14, 5, 9).toISOString(), actor_user_id: 'u1', actor_username: 'ana',
  application_id: 'a-leo', module: 'users', action_tag: 'leo.users.edit', entity_type: 'user', entity_id: 'u-42',
  changes: { first_name: { before: 'Ana', after: 'Ana María' }, password_hash: { before: 'x', after: 'y' } },
  result: 'ok', reason: 'Edición de usuario.', ip: '10.0.0.7',
  user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
  session_id: 's-1', request_id: 'req-123', ...over
})
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 25 })
const leoDetail = {
  id: 'a-leo', slug: 'leo', name: 'Leo',
  modules: [{ slug: 'users', name: 'Usuarios', actions: [{ tag: 'leo.users.edit', name: 'Editar usuario' }, { tag: 'leo.users.view', name: 'Consultar usuarios' }] }]
}

/** Enruta la API por ruta; `events` es lo que devuelve el listado. */
function route(events: unknown[], over: Record<string, unknown> = {}) {
  const handlers: Record<string, unknown> = {
    '/audit/events': page(events),
    '/applications': { items: [{ id: 'a-leo', slug: 'leo', name: 'Leo' }], total: 1, page: 1, page_size: 200 },
    '/applications/a-leo': leoDetail,
    '/users': { items: [{ id: 'u1', username: 'ana', first_name: 'Ana', last_name: 'Pérez' }], total: 1, page: 1, page_size: 200 },
    ...over
  }
  api.mockImplementation(async (url: string) => {
    const h = handlers[url]
    if (h === undefined) throw new Error(`sin handler: ${url}`)
    if (h instanceof Error) throw h
    return h
  })
}
/** Filas del cuerpo de la tabla (sin la cabecera). */
const bodyRows = (w: VueWrapper) => w.findAll('tr').slice(1)
const eventCalls = () => api.mock.calls.filter(c => c[0] === '/audit/events')

beforeEach(() => {
  api.mockReset()
  download.mockReset()
  signInWith(ALL_AUDIT_TAGS)
  route([event(), event({ id: 'e2', result: 'denied', actor_username: null, actor_user_id: null, module: null, entity_type: null, entity_id: null, changes: null })])
})
afterEach(() => { document.body.innerHTML = '' })

async function mountList() {
  const wrapper = await mountSuspended(AuditList, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('AuditList', () => {
  it('pide la primera página y muestra quién, aplicación → módulo, acción legible, sobre qué y resultado', async () => {
    const wrapper = await mountList()
    expect(api).toHaveBeenCalledWith('/audit/events', { query: { page: 1, page_size: 25 } })
    const row = bodyRows(wrapper)[0]!
    expect(row.get('[data-testid="audit-when"]').text()).toBe('19/10/2026 14:05')
    expect(row.get('[data-testid="audit-actor"]').text()).toBe('ana')
    expect(row.get('[data-testid="audit-context"]').text().replace(/\s+/g, ' ')).toBe('Leo → Usuarios')
    expect(row.get('[data-testid="audit-action"]').text()).toBe('Editar usuario')
    expect(row.text()).toContain('leo.users.edit')
    expect(row.get('[data-testid="audit-entity"]').text()).toContain('Usuario')
    expect(row.get('[data-testid="audit-entity"]').text()).toContain('u-42')
    expect(row.get('[data-testid="audit-result"]').text()).toBe('Permitido')
  })

  it('un evento sin usuario es del «Sistema»; denegado y sin entidad', async () => {
    const wrapper = await mountList()
    const row = bodyRows(wrapper)[1]!
    expect(row.get('[data-testid="audit-actor"]').text()).toBe('Sistema')
    expect(row.get('[data-testid="audit-result"]').text()).toBe('Denegado')
    expect(row.get('[data-testid="audit-result"]').attributes('data-result')).toBe('denied')
    expect(row.find('[data-testid="audit-entity"]').exists()).toBe(false)
  })

  it('Buscar aplica los filtros (resultado y fechas) y vuelve a la página 1', async () => {
    const wrapper = await mountList()
    await wrapper.get('[data-testid="filter-result"]').setValue('denied')
    await wrapper.get('[data-testid="filter-date-from"]').setValue('2026-10-01')
    await wrapper.get('[data-testid="filter-date-to"]').setValue('2026-10-19')
    await wrapper.get('[data-testid="audit-filters"]').trigger('submit')
    await flushPromises()
    expect(eventCalls().at(-1)![1]).toEqual({
      query: {
        page: 1, page_size: 25, result: 'denied',
        date_from: new Date(2026, 9, 1).toISOString(), date_to: new Date(2026, 9, 20).toISOString()
      }
    })
  })

  it('módulo y acción dependen de la aplicación elegida y muestran nombres', async () => {
    const wrapper = await mountList()
    expect(wrapper.get('[data-testid="filter-module"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="filter-app"]').setValue('a-leo')
    await flushPromises()
    const modules = wrapper.get('[data-testid="filter-module"]').findAll('option').map(o => o.text())
    expect(modules).toContain('Usuarios')
    const actions = wrapper.get('[data-testid="filter-action"]').findAll('option').map(o => o.text())
    expect(actions).toEqual(expect.arrayContaining(['Editar usuario', 'Consultar usuarios']))
    await wrapper.get('[data-testid="filter-action"]').setValue('leo.users.edit')
    await wrapper.get('[data-testid="audit-filters"]').trigger('submit')
    await flushPromises()
    expect(eventCalls().at(-1)![1].query).toMatchObject({ application_id: 'a-leo', action_tag: 'leo.users.edit' })
  })

  it('Limpiar filtros vacía el formulario y consulta sin filtros', async () => {
    const wrapper = await mountList()
    await wrapper.get('[data-testid="filter-result"]').setValue('error')
    await wrapper.get('[data-testid="filter-clear"]').trigger('click')
    await flushPromises()
    expect(eventCalls().at(-1)![1]).toEqual({ query: { page: 1, page_size: 25 } })
  })

  it('Ver detalle abre el evento con IP, navegador, request_id y el diff', async () => {
    const wrapper = await mountList()
    await wrapper.findAll('[data-testid="audit-view"]')[0]!.trigger('click')
    await flushPromises()
    const detail = document.body.querySelector('[data-testid="audit-detail"]')!
    expect(detail.textContent).toContain('10.0.0.7')
    expect(detail.textContent).toContain('Chrome 141 en Windows')
    expect(detail.textContent).toContain('req-123')
    expect(detail.textContent).toContain('19/10/2026 14:05:09')
    const rows = [...detail.querySelectorAll('[data-testid="diff-row"]')]
    expect(rows).toHaveLength(2)
    const nombres = rows.find(r => r.getAttribute('data-kind') === 'changed' && r.textContent?.includes('Nombres'))!
    expect(nombres.querySelector('[data-testid="diff-before"]')!.textContent).toContain('Ana')
    expect(nombres.querySelector('[data-testid="diff-after"]')!.textContent).toContain('Ana María')
    expect(detail.textContent).not.toContain('"x"')
  })

  it('un evento sin cambios lo dice en el detalle', async () => {
    const wrapper = await mountList()
    await wrapper.findAll('[data-testid="audit-view"]')[1]!.trigger('click')
    await flushPromises()
    expect(document.body.querySelector('[data-testid="diff-empty"]')!.textContent).toContain('no registra cambios')
  })

  it('exporta con los filtros vigentes y guarda el blob como archivo', async () => {
    const blob = new Blob(['a;b'])
    route([event()], { '/audit/events/export': blob })
    const wrapper = await mountList()
    await wrapper.get('[data-testid="filter-result"]').setValue('ok')
    await wrapper.get('[data-testid="audit-filters"]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-testid="audit-export"]').trigger('click')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/audit/events/export', { query: { result: 'ok' }, responseType: 'blob' })
    expect(download).toHaveBeenCalledWith(blob, expect.stringMatching(/^auditoria-\d{4}-\d{2}-\d{2}\.csv$/))
  })

  it('si la exportación falla muestra un mensaje legible y no descarga', async () => {
    route([event()], { '/audit/events/export': new LeoApiError(403, 'forbidden', 'No tienes permiso para exportar.') })
    const wrapper = await mountList()
    await wrapper.get('[data-testid="audit-export"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="audit-export-error"]').text()).toContain('No tienes permiso para exportar.')
    expect(download).not.toHaveBeenCalled()
  })

  it('sin leo.audit.export no hay botón de exportar', async () => {
    signInWith(['leo.audit.view'])
    const wrapper = await mountList()
    expect(wrapper.find('[data-testid="audit-export"]').exists()).toBe(false)
  })

  it('error del listado: mensaje legible, nunca la respuesta cruda', async () => {
    route([], { '/audit/events': new LeoApiError(500, 'internal', 'Traceback (most recent call last)') })
    const wrapper = await mountList()
    const text = wrapper.get('[data-testid="audit-error"]').text()
    expect(text).not.toContain('Traceback')
    expect(text.length).toBeGreaterThan(0)
  })

  it('si no se pueden leer los catálogos, avisa y muestra los identificadores técnicos', async () => {
    route([event()], { '/applications/a-leo': new LeoApiError(403, 'forbidden', 'No tienes permiso.'), '/applications': new LeoApiError(403, 'forbidden', 'No tienes permiso.') })
    const wrapper = await mountList()
    expect(wrapper.find('[data-testid="audit-lookup-error"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="audit-action"]').text()).toBe('leo.users.edit')
    expect(wrapper.get('[data-testid="audit-context"]').text()).toContain('Aplicación desconocida')
  })
})
