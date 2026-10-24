import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_ROLES_TAGS, signInWith } from '../../../../tests/helpers/session'
import RolesDetail from './RolesDetail.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const act = (id: string, verb: string, name: string, extra: Record<string, unknown> = {}) => ({
  id, verb, tag: `vladimir.samples.${verb}`, name, description: `Desc ${name}`, is_active: true, ...extra
})
const catalog = {
  id: 'app1', slug: 'vladimir', name: 'Vladimir',
  modules: [{
    id: 'm1', slug: 'samples', name: 'Muestras', description: null, is_active: true,
    actions: [act('a1', 'view', 'Consultar muestras'), act('a2', 'edit', 'Editar muestras'), act('e1', 'login', 'Inicio', { description: 'Evento: x' })]
  }]
}
const assignedAction = (id: string, name: string) => ({
  id, tag: `vladimir.samples.${id}`, verb: id, name, description: null, is_active: true, module: { id: 'm1', slug: 'samples', name: 'Muestras' }
})
const roleDetail = (actions: unknown[], over: Record<string, unknown> = {}) => ({
  id: 'r1', application_id: 'app1', slug: 'analista', name: 'Analista', description: 'Rol de prueba', is_active: true,
  created_at: '', updated_at: '', actions, ...over
})

/** Enruta las llamadas de la API por método y ruta. */
function route(handlers: Record<string, unknown | ((o: any) => unknown)>) {
  api.mockImplementation(async (url: string, opts: { method?: string } = {}) => {
    const key = `${opts.method ?? 'GET'} ${url}`
    const h = handlers[key]
    if (h === undefined) throw new Error(`sin handler: ${key}`)
    const out = typeof h === 'function' ? (h as (o: unknown) => unknown)(opts) : h
    if (out instanceof Error) throw out
    return out
  })
}

const byId = (id: string) => document.body.querySelector<HTMLElement>(`[data-testid="${id}"]`)

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_ROLES_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

async function mountDetail(handlers: Record<string, unknown | ((o: any) => unknown)>) {
  route({ 'GET /roles/r1': roleDetail([assignedAction('a1', 'Consultar muestras')]), 'GET /applications/app1': catalog, ...handlers })
  const wrapper = await mountSuspended(RolesDetail, { props: { id: 'r1' }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

const checks = (wrapper: Awaited<ReturnType<typeof mountDetail>>) => wrapper.findAll('[data-testid="permission-check"] input')

describe('RolesDetail', () => {
  it('muestra datos del rol, la app y los permisos asignados marcados', async () => {
    const wrapper = await mountDetail({})
    expect(wrapper.text()).toContain('Analista')
    expect(wrapper.get('[data-testid="role-app"]').text()).toBe('Vladimir')
    expect(api).toHaveBeenCalledWith('/applications/app1')
    const boxes = checks(wrapper)
    expect(boxes).toHaveLength(2)
    expect((boxes[0]!.element as HTMLInputElement).checked).toBe(true)
    expect((boxes[1]!.element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.get('[data-testid="change-summary"]').text()).toBe('Sin cambios pendientes.')
  })

  it('agregar permisos: un POST con lo nuevo y mensaje de éxito', async () => {
    const after = roleDetail([assignedAction('a1', 'Consultar muestras'), assignedAction('a2', 'Editar muestras')])
    const wrapper = await mountDetail({ 'POST /roles/r1/actions': after })
    await checks(wrapper)[1]!.setValue(true)
    expect(wrapper.get('[data-testid="change-summary"]').text()).toContain('1 por agregar')
    await wrapper.get('[data-testid="save"]').trigger('click')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/roles/r1/actions', { method: 'POST', body: { action_ids: ['a2'] } })
    expect(wrapper.get('[data-testid="change-summary"]').text()).toBe('Sin cambios pendientes.')
    expect(api.mock.calls.some(([, o]) => o?.method === 'DELETE')).toBe(false)
  })

  it('quitar permisos: un DELETE por acción quitada', async () => {
    const wrapper = await mountDetail({ 'DELETE /roles/r1/actions/a1': roleDetail([]) })
    await checks(wrapper)[0]!.setValue(false)
    expect(wrapper.get('[data-testid="change-summary"]').text()).toContain('1 por quitar')
    await wrapper.get('[data-testid="save"]').trigger('click')
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/roles/r1/actions/a1', { method: 'DELETE' })
    expect(api.mock.calls.some(([, o]) => o?.method === 'POST')).toBe(false)
  })

  it('«Seleccionar todo» del módulo envía todos los asignables en un solo POST', async () => {
    const after = roleDetail([assignedAction('a1', 'Consultar muestras'), assignedAction('a2', 'Editar muestras')])
    const wrapper = await mountDetail({ 'POST /roles/r1/actions': after })
    await wrapper.get('[data-testid="group-all"] input').setValue(true)
    await wrapper.get('[data-testid="save"]').trigger('click')
    await flushPromises()
    const posts = api.mock.calls.filter(([, o]) => o?.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(posts[0]![1].body).toEqual({ action_ids: ['a2'] })
  })

  it('descartar vuelve a lo asignado', async () => {
    const wrapper = await mountDetail({})
    await checks(wrapper)[1]!.setValue(true)
    await wrapper.get('[data-testid="discard"]').trigger('click')
    expect((checks(wrapper)[1]!.element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.get('[data-testid="change-summary"]').text()).toBe('Sin cambios pendientes.')
  })

  it('error al guardar: mensaje legible, conserva el borrador y recarga el rol', async () => {
    const wrapper = await mountDetail({
      'POST /roles/r1/actions': new LeoApiError(422, 'invalid_reference', 'Algunas acciones no existen o no son de la aplicación del rol.')
    })
    await checks(wrapper)[1]!.setValue(true)
    await wrapper.get('[data-testid="save"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="save-error"]').text()).toContain('Algunos permisos ya no están disponibles')
    expect(wrapper.get('[data-testid="change-summary"]').text()).toContain('1 por agregar')
    expect(api.mock.calls.filter(([url, o]) => url === '/roles/r1' && !o).length).toBeGreaterThanOrEqual(2)
  })

  it('error de red al guardar: nunca el texto crudo', async () => {
    const wrapper = await mountDetail({ 'POST /roles/r1/actions': new TypeError('Failed to fetch') })
    await checks(wrapper)[1]!.setValue(true)
    await wrapper.get('[data-testid="save"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="save-error"]').text()).not.toMatch(/fetch/i)
  })

  it('sin leo.roles.edit: permisos concedidos en texto, sin casillas ni barra de guardado ni Editar', async () => {
    signInWith(['leo.roles.view'])
    const wrapper = await mountDetail({})
    expect(wrapper.find('input').exists()).toBe(false)
    const granted = wrapper.findAll('[data-testid="permission-granted"]')
    expect(granted).toHaveLength(1)
    expect(granted[0]!.text()).toContain('Consultar muestras')
    expect(wrapper.text()).not.toContain('Editar muestras')
    expect(wrapper.find('[data-testid="save-bar"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="role-edit"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="role-toggle"]').exists()).toBe(false)
  })

  it('catálogo no disponible (403): aviso y solo lo asignado, en solo lectura', async () => {
    const wrapper = await mountDetail({ 'GET /applications/app1': new LeoApiError(403, 'forbidden', 'No tienes permiso para esta acción.') })
    expect(wrapper.get('[data-testid="catalog-error"]').text()).toContain('No tienes permiso para esta acción.')
    expect(wrapper.find('input').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="permission-granted"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="save-bar"]').exists()).toBe(false)
  })

  it('desactivar pide confirmación y llama a la API', async () => {
    const wrapper = await mountDetail({ 'POST /roles/r1/deactivate': roleDetail([], { is_active: false }) })
    await wrapper.get('[data-testid="role-toggle"]').trigger('click')
    expect(document.body.textContent).toContain('Se desactivará «Analista»')
    const confirm = [...document.body.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Desactivar' && b.closest('[role="dialog"]'))!
    confirm.click()
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/roles/r1/deactivate', { method: 'POST' })
  })

  it('error de carga (404): mensaje legible del backend', async () => {
    route({ 'GET /roles/zzz': new LeoApiError(404, 'not_found', 'No se encontró el rol.') })
    const wrapper = await mountSuspended(RolesDetail, { props: { id: 'zzz' }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.get('[data-testid="detail-error"]').text()).toContain('No se encontró el rol.')
    expect(byId('save-bar')).toBeNull()
  })

  describe('aplicaciones con acceso de servicio', () => {
    const callers = [{ id: 'c1', application: { id: 'app9', slug: 'incubus', name: 'Incubus', is_active: true }, created_at: '' }]

    it('con el permiso: lista las apps con enlace a su detalle (solo lectura)', async () => {
      signInWith([...ALL_ROLES_TAGS, 'leo.applications.grant-service-access'])
      const wrapper = await mountDetail({ 'GET /roles/r1/service-callers': callers })
      expect(api).toHaveBeenCalledWith('/roles/r1/service-callers')
      const link = wrapper.get('[data-testid="caller-link"]')
      expect(link.text()).toBe('Incubus')
      expect(link.attributes('href')).toBe('/applications/app9')
    })

    it('sin apps: texto vacío', async () => {
      signInWith([...ALL_ROLES_TAGS, 'leo.applications.grant-service-access'])
      const wrapper = await mountDetail({ 'GET /roles/r1/service-callers': [] })
      expect(wrapper.get('[data-testid="callers-empty"]').text()).toContain('Ninguna aplicación')
    })

    it('error: mensaje legible del backend', async () => {
      signInWith([...ALL_ROLES_TAGS, 'leo.applications.grant-service-access'])
      const wrapper = await mountDetail({ 'GET /roles/r1/service-callers': new LeoApiError(403, 'forbidden', 'No tienes acceso.') })
      expect(wrapper.get('[data-testid="callers-error"]').text()).toContain('No tienes acceso.')
    })

    it('sin el permiso no se renderiza ni se consulta', async () => {
      const wrapper = await mountDetail({})
      expect(wrapper.find('[data-testid="service-callers"]').exists()).toBe(false)
      expect(api).not.toHaveBeenCalledWith('/roles/r1/service-callers')
    })
  })
})
