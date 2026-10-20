import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_APPLICATIONS_TAGS, signInWith } from '../../../../tests/helpers/session'
import ApplicationsDetail from './ApplicationsDetail.vue'
import ApplicationsServiceAccess from './ApplicationsServiceAccess.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const perm = (id: string, name: string) => ({
  id, tag: `vladimir.samples.${id}`, verb: id, name, description: null, is_active: true, module: { id: 'm1', slug: 'samples', name: 'Muestras' }
})
const grant = (id: string, roleName: string, extra: Record<string, unknown> = {}) => ({
  id,
  role: { id: `r-${id}`, slug: roleName.toLowerCase(), name: roleName, is_active: true },
  application: { id: 'v1', slug: 'vladimir', name: 'Vladimir' },
  permissions: [perm('view', 'Consultar muestras')],
  created_at: '',
  ...extra
})
const appRow = (id: string, slug: string, name: string) => ({
  id, slug, name, description: null, base_url: '', redirect_uris: [], client_id: slug, is_active: true, created_at: '', updated_at: ''
})

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

const body = () => document.body
const byId = (id: string) => body().querySelector<HTMLElement>(`[data-testid="${id}"]`)
const click = async (id: string) => { byId(id)!.click(); await flushPromises() }
const dialogButton = (label: string) =>
  [...body().querySelectorAll('[role="dialog"] button')].find(b => b.textContent?.trim() === label) as HTMLElement

async function mountSection(handlers: Record<string, unknown | ((o: any) => unknown)> = {}) {
  route({ 'GET /applications/i1/service-access': [grant('g1', 'Lector'), grant('g2', 'Analista')], ...handlers })
  const wrapper = await mountSuspended(ApplicationsServiceAccess, { props: { appId: 'i1', appName: 'Incubus' }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_APPLICATIONS_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

describe('ApplicationsServiceAccess (lista)', () => {
  it('agrupa por aplicación destino, roles por nombre, con permisos legibles y tag pequeño', async () => {
    const wrapper = await mountSection()
    const groups = wrapper.findAll('[data-testid="service-group"]')
    expect(groups).toHaveLength(1)
    expect(groups[0]!.text()).toContain('Vladimir')
    expect(wrapper.findAll('[data-testid="grant-role-name"]').map(e => e.text())).toEqual(['Rol: Analista', 'Rol: Lector'])
    expect(wrapper.find('[data-testid="perm-name"]').text()).toBe('Consultar muestras')
    const tag = wrapper.find('[data-testid="perm-tag"]')
    expect(tag.text()).toBe('vladimir.samples.view')
    expect(tag.classes()).toContain('text-xs')
  })

  it('muestra el aviso permanente de tokens de servicio', async () => {
    const wrapper = await mountSection()
    expect(wrapper.get('[data-testid="service-ttl-notice"]').text()).toBe('Los tokens de servicio duran minutos y no se atan a un dispositivo.')
  })

  it('sin concesiones: texto vacío', async () => {
    const wrapper = await mountSection({ 'GET /applications/i1/service-access': [] })
    expect(wrapper.get('[data-testid="service-empty"]').text()).toContain('no tiene acceso concedido')
  })

  it('error de carga: legible', async () => {
    const wrapper = await mountSection({ 'GET /applications/i1/service-access': new LeoApiError(403, 'forbidden', 'No tienes acceso.') })
    expect(wrapper.get('[data-testid="service-error"]').text()).toContain('No tienes acceso.')
  })
})

describe('ApplicationsServiceAccess (quitar)', () => {
  it('pide confirmación advirtiendo la revocación inmediata y llama al DELETE', async () => {
    const wrapper = await mountSection({ 'DELETE /applications/i1/service-access/r-g2': {} })
    await wrapper.findAll('[data-testid="grant-revoke"]')[0]!.trigger('click')
    expect(body().textContent).toContain('Sus tokens de servicio con este rol se revocan de inmediato')
    expect(body().textContent).toContain('«Analista»')
    dialogButton('Quitar acceso').click()
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/applications/i1/service-access/r-g2', { method: 'DELETE' })
  })

  it('si falla muestra el error legible en el modal', async () => {
    const wrapper = await mountSection({ 'DELETE /applications/i1/service-access/r-g2': new LeoApiError(403, 'forbidden', 'No tienes acceso.') })
    await wrapper.findAll('[data-testid="grant-revoke"]')[0]!.trigger('click')
    dialogButton('Quitar acceso').click()
    await flushPromises()
    expect(body().textContent).toContain('No tienes acceso.')
  })
})

describe('ApplicationsServiceAccess (conceder)', () => {
  const handlers = (post: unknown = [grant('g3', 'Lector')]) => ({
    'GET /applications': { items: [appRow('i1', 'incubus', 'Incubus'), appRow('l1', 'leo', 'Leo'), appRow('v1', 'vladimir', 'Vladimir')], total: 3, page: 1, page_size: 200 },
    'GET /roles': { items: [{ id: 'r1', slug: 'lector', name: 'Lector', description: 'Solo lectura', is_active: true }], total: 1 },
    'GET /roles/r1': { id: 'r1', actions: [perm('view', 'Consultar muestras')] },
    'POST /applications/i1/service-access': post
  })

  async function pickTarget() {
    const select = byId('grant-target')!.querySelector('select') ?? byId('grant-target') as HTMLSelectElement
    ;(select as HTMLSelectElement).value = 'v1'
    select.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
  }

  async function open(extra: Record<string, unknown> = {}) {
    const wrapper = await mountSection(handlers())
    route({ 'GET /applications/i1/service-access': [], ...handlers(), ...extra })
    await click('grant-open')
    return wrapper
  }

  it('el selector no ofrece la app actual ni leo; pide roles activos de la elegida', async () => {
    await open()
    const options = [...body().querySelectorAll('[data-testid="grant-target"] option, select[data-testid="grant-target"] option')].map(o => o.textContent?.trim())
    expect(options).toContain('Vladimir')
    expect(options).not.toContain('Incubus')
    expect(options).not.toContain('Leo')
    await pickTarget()
    expect(api).toHaveBeenCalledWith('/roles', { query: { application_id: 'v1', active: true, page: 1, page_size: 200 } })
    expect(byId('grant-role')!.textContent).toContain('Lector')
    expect(byId('grant-role')!.textContent).toContain('Consultar muestras')
  })

  it('sin roles marcados no se puede conceder; al marcar muestra el texto claro y hace un POST', async () => {
    await open()
    await pickTarget()
    expect(byId('grant-submit')!.hasAttribute('disabled')).toBe(true)
    byId('grant-role-check')!.querySelector<HTMLInputElement>('input')!.click()
    await flushPromises()
    expect(byId('grant-summary')!.textContent).toContain('Incubus podrá consultar Vladimir con los permisos de estos roles.')
    await click('grant-submit')
    expect(api).toHaveBeenCalledWith('/applications/i1/service-access', { method: 'POST', body: { role_ids: ['r1'] } })
  })

  it('error 422 same_application: texto legible, el modal sigue abierto', async () => {
    await open({ 'POST /applications/i1/service-access': new LeoApiError(422, 'same_application', 'x', { role_ids: ['r1'] }) })
    await pickTarget()
    byId('grant-role-check')!.querySelector<HTMLInputElement>('input')!.click()
    await flushPromises()
    await click('grant-submit')
    expect(byId('grant-error')!.textContent).toContain('otra aplicación')
  })
})

describe('permiso leo.applications.grant-service-access en el detalle', () => {
  const detail = {
    id: 'i1', slug: 'incubus', name: 'Incubus', description: null, base_url: 'https://i.test', redirect_uris: [], client_id: 'incubus',
    is_active: true, created_at: '', updated_at: '', modules: []
  }

  it('sin el tag la sección no se renderiza ni consulta', async () => {
    signInWith(ALL_APPLICATIONS_TAGS.filter(t => t !== 'leo.applications.grant-service-access'))
    api.mockResolvedValue(detail)
    const wrapper = await mountSuspended(ApplicationsDetail, { props: { id: 'i1' }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('[data-testid="service-access"]').exists()).toBe(false)
    expect(api).not.toHaveBeenCalledWith('/applications/i1/service-access')
  })

  it('con el tag aparece en el detalle', async () => {
    api.mockImplementation(async (url: string) => (url.endsWith('/service-access') ? [] : detail))
    const wrapper = await mountSuspended(ApplicationsDetail, { props: { id: 'i1' }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('[data-testid="service-access"]').exists()).toBe(true)
  })

  it('la app leo (solo lectura) no ofrece la sección', async () => {
    api.mockResolvedValue({ ...detail, slug: 'leo', name: 'Leo' })
    const wrapper = await mountSuspended(ApplicationsDetail, { props: { id: 'i1' }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('[data-testid="service-access"]').exists()).toBe(false)
  })
})
