import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_ROLES_TAGS, signInWith } from '../../../../tests/helpers/session'
import RolesFormModal from './RolesFormModal.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const applications = [
  { id: 'app1', slug: 'vladimir', name: 'Vladimir', is_active: true },
  { id: 'app2', slug: 'old', name: 'Vieja', is_active: false }
]
const saved = { id: 'r1', application_id: 'app1', slug: 'analista', name: 'Analista', description: null, is_active: true, created_at: '', updated_at: '' }

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_ROLES_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

const dialog = () => document.body.querySelector('[role="dialog"]')!
const select = () => dialog().querySelector<HTMLSelectElement>('select')!
const texts = () => [...dialog().querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input, textarea')]
async function type(el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, value: string) {
  el.value = value
  el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }))
  await flushPromises()
}
const submit = () => dialog().querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit', { cancelable: true }))

describe('RolesFormModal', () => {
  it('crear: solo ofrece aplicaciones activas y llama a POST /roles con el payload', async () => {
    api.mockResolvedValue(saved)
    const wrapper = await mountSuspended(RolesFormModal, { props: { open: true, applications }, attachTo: document.body })
    expect([...select().options].map(o => o.textContent?.trim())).toEqual(['Elige una aplicación', 'Vladimir'])
    await type(select(), 'app1')
    await type(texts()[0]!, 'analista')
    await type(texts()[1]!, ' Analista ')
    submit()
    await vi.waitFor(() => expect(api).toHaveBeenCalled())
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/roles', { method: 'POST', body: { application_id: 'app1', slug: 'analista', name: 'Analista', description: null } })
    expect(wrapper.emitted('saved')?.[0]).toEqual([saved])
  })

  it('crear: aplicación elegida por defecto (la del filtro)', async () => {
    await mountSuspended(RolesFormModal, { props: { open: true, applications, defaultApplicationId: 'app1' }, attachTo: document.body })
    expect(select().value).toBe('app1')
  })

  it('crear: slug inválido y aplicación vacía no llaman a la API', async () => {
    await mountSuspended(RolesFormModal, { props: { open: true, applications }, attachTo: document.body })
    await type(texts()[0]!, 'Mi Rol')
    await type(texts()[1]!, 'Nombre')
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Usa minúsculas'))
    expect(document.body.textContent).toContain('Elige la aplicación del rol.')
    expect(api).not.toHaveBeenCalled()
  })

  it('slug repetido (409 duplicate): error en el campo del identificador', async () => {
    api.mockRejectedValue(new LeoApiError(409, 'duplicate', 'Ya existe un rol en esta aplicación con el slug «analista».', { slug: 'analista' }))
    await mountSuspended(RolesFormModal, { props: { open: true, applications, defaultApplicationId: 'app1' }, attachTo: document.body })
    await type(texts()[0]!, 'analista')
    await type(texts()[1]!, 'Analista')
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ya existe un rol en esta aplicación'))
    const alert = [...dialog().querySelectorAll('[role="alert"]')].find(a => a.textContent?.includes('Ya existe'))!
    expect(alert.closest('.flex.flex-col')?.textContent).toContain('Identificador')
  })

  it('editar: aplicación y slug bloqueados; solo envía nombre y descripción', async () => {
    api.mockResolvedValue({ ...saved, name: 'Nuevo' })
    await mountSuspended(RolesFormModal, { props: { open: true, applications, role: saved }, attachTo: document.body })
    expect(select().disabled).toBe(true)
    expect(select().value).toBe('app1')
    expect(texts()[0]!.disabled).toBe(true)
    expect(texts()[0]!.value).toBe('analista')
    await type(texts()[1]!, 'Nuevo')
    submit()
    await vi.waitFor(() => expect(api).toHaveBeenCalled())
    expect(api).toHaveBeenCalledWith('/roles/r1', { method: 'PATCH', body: { name: 'Nuevo', description: null } })
  })
})
