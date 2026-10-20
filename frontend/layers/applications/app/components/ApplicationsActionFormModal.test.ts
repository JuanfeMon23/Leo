import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ALL_APPLICATIONS_TAGS, signInWith } from '../../../../tests/helpers/session'
import ApplicationsActionFormModal from './ApplicationsActionFormModal.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const props = { open: true, appId: 'a1', appSlug: 'vladimir', moduleId: 'm1', moduleSlug: 'samples' }

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_APPLICATIONS_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

const submit = () => document.body.querySelector<HTMLFormElement>('[role="dialog"] form')!.dispatchEvent(new Event('submit', { cancelable: true }))
const preview = () => document.body.querySelector('[data-testid="tag-preview"]')!.textContent
const inputs = () => [...document.body.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('[role="dialog"] input, [role="dialog"] textarea')]

async function type(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
  el.value = value
  el.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}

describe('ApplicationsActionFormModal', () => {
  it('muestra el tag resultante en vivo mientras se escribe el verbo', async () => {
    await mountSuspended(ApplicationsActionFormModal, { props, attachTo: document.body })
    expect(preview()).toBe('vladimir.samples.‹verbo›')
    await type(inputs()[1]!, 'rotate')
    expect(preview()).toBe('vladimir.samples.rotate')
    await type(inputs()[1]!, 'rotate-secret')
    expect(preview()).toBe('vladimir.samples.rotate-secret')
  })

  it('crear: llama a la API del módulo con nombre y verbo y emite saved', async () => {
    const saved = { id: 'x', module_id: 'm1', verb: 'view', tag: 'vladimir.samples.view', name: 'Consultar muestras', description: null, is_active: true }
    api.mockResolvedValue(saved)
    const wrapper = await mountSuspended(ApplicationsActionFormModal, { props, attachTo: document.body })
    await type(inputs()[0]!, ' Consultar muestras ')
    await type(inputs()[1]!, 'view')
    submit()
    await vi.waitFor(() => expect(api).toHaveBeenCalled())
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/applications/a1/modules/m1/actions', { method: 'POST', body: { verb: 'view', name: 'Consultar muestras', description: null } })
    expect(wrapper.emitted('saved')?.[0]).toEqual([saved])
  })

  it('verbo inválido: error de validación y no llama a la API', async () => {
    await mountSuspended(ApplicationsActionFormModal, { props, attachTo: document.body })
    await type(inputs()[0]!, 'Consultar')
    await type(inputs()[1]!, 'Ver Todo')
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Usa minúsculas'))
    expect(api).not.toHaveBeenCalled()
  })

  it('nombre vacío: error en el campo y no llama a la API', async () => {
    await mountSuspended(ApplicationsActionFormModal, { props, attachTo: document.body })
    await type(inputs()[1]!, 'view')
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('El nombre del permiso es obligatorio.'))
    expect(api).not.toHaveBeenCalled()
  })

  it('409 duplicate sobre el nombre: error en el campo «Nombre del permiso»', async () => {
    const { LeoApiError } = await import('#leo-client/lib/errors')
    api.mockRejectedValue(new LeoApiError(409, 'duplicate', 'Ya existe una acción en este módulo con el nombre «Consultar muestras».', { name: 'Consultar muestras' }))
    await mountSuspended(ApplicationsActionFormModal, { props, attachTo: document.body })
    await type(inputs()[0]!, 'Consultar muestras')
    await type(inputs()[1]!, 'view')
    submit()
    await vi.waitFor(() => expect(document.body.querySelector('[role="alert"]')?.textContent).toContain('Ya existe una acción en este módulo'))
    const alert = [...document.body.querySelectorAll('[role="alert"]')].find(a => a.textContent?.includes('Ya existe'))!
    expect(alert.closest('.flex.flex-col')?.textContent).toContain('Nombre del permiso')
  })

  it('409 event_action_readonly: mensaje legible en el formulario', async () => {
    const { LeoApiError } = await import('#leo-client/lib/errors')
    const action = { id: 'x', module_id: 'm1', verb: 'view', tag: 'vladimir.samples.view', name: 'Ver', description: 'Ver', is_active: true }
    api.mockRejectedValue(new LeoApiError(409, 'event_action_readonly', '«vladimir.samples.view» es una acción de evento (solo se audita): no se puede editar.', { tag: 'x' }))
    await mountSuspended(ApplicationsActionFormModal, { props: { ...props, action }, attachTo: document.body })
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('es una acción de evento'))
  })

  it('editar: carga el nombre, verbo bloqueado, tag real y envía nombre y descripción', async () => {
    const action = { id: 'x', module_id: 'm1', verb: 'view', tag: 'vladimir.samples.view', name: 'Consultar muestras', description: 'Ver', is_active: true }
    api.mockResolvedValue({ ...action, name: 'Ver muestras' })
    await mountSuspended(ApplicationsActionFormModal, { props: { ...props, action }, attachTo: document.body })
    expect(inputs()[0]!.value).toBe('Consultar muestras')
    expect(inputs()[1]!.disabled).toBe(true)
    expect(preview()).toBe('vladimir.samples.view')
    await type(inputs()[0]!, 'Ver muestras')
    submit()
    await vi.waitFor(() => expect(api).toHaveBeenCalled())
    expect(api).toHaveBeenCalledWith('/applications/a1/actions/x', { method: 'PATCH', body: { name: 'Ver muestras', description: 'Ver' } })
  })
})
