import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_APPLICATIONS_TAGS, signInWith } from '../../../../tests/helpers/session'
import ApplicationsFormModal from './ApplicationsFormModal.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const created = {
  application: { id: 'a1', slug: 'mi-app', name: 'Mi app', description: null, base_url: 'https://m.test', redirect_uris: ['https://m.test/cb'], client_id: 'mi-app', is_active: true, created_at: '', updated_at: '' },
  client_secret: 'SECRETO'
}

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_APPLICATIONS_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

const field = (name: string) => document.body.querySelector<HTMLInputElement | HTMLTextAreaElement>(`[name="${name}"], #${name}`)
function inputs() {
  return [...document.body.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('[role="dialog"] input, [role="dialog"] textarea')]
}
async function fill(values: string[]) {
  const els = inputs()
  for (const [i, v] of values.entries()) {
    els[i]!.value = v
    els[i]!.dispatchEvent(new Event('input', { bubbles: true }))
  }
  await flushPromises()
}
async function submit() {
  document.body.querySelector<HTMLFormElement>('[role="dialog"] form')!.dispatchEvent(new Event('submit', { cancelable: true }))
  await flushPromises()
}

describe('ApplicationsFormModal', () => {
  it('crear con datos vacíos: errores de validación y no llama a la API', async () => {
    await mountSuspended(ApplicationsFormModal, { props: { open: true }, attachTo: document.body })
    await submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('El identificador es obligatorio.'))
    const text = document.body.textContent!
    expect(text).toContain('El nombre es obligatorio.')
    expect(text).toContain('La URL base es obligatoria.')
    expect(api).not.toHaveBeenCalled()
  })

  it('slug con mayúsculas: error de kebab-case', async () => {
    await mountSuspended(ApplicationsFormModal, { props: { open: true }, attachTo: document.body })
    await fill(['Mi App', 'Mi app', '', 'https://m.test', ''])
    await submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Usa minúsculas, números y guiones'))
    expect(api).not.toHaveBeenCalled()
  })

  it('crear: envía el payload y emite created con el secreto', async () => {
    api.mockResolvedValue(created)
    const wrapper = await mountSuspended(ApplicationsFormModal, { props: { open: true }, attachTo: document.body })
    await fill(['mi-app', 'Mi app', '', 'https://m.test', 'https://m.test/cb\nhttps://m.test/cb2'])
    await submit()
    await vi.waitFor(() => expect(api).toHaveBeenCalled())
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/applications', {
      method: 'POST',
      body: {
        slug: 'mi-app', name: 'Mi app', description: null, base_url: 'https://m.test',
        redirect_uris: ['https://m.test/cb', 'https://m.test/cb2']
      }
    })
    expect(wrapper.emitted('created')?.[0]).toEqual([created])
    expect(wrapper.emitted('update:open')?.at(-1)).toEqual([false])
  })

  it('error del backend (409): mensaje legible en el formulario y no se cierra', async () => {
    api.mockImplementation(() => Promise.reject(new LeoApiError(409, 'duplicate_value', 'Ya existe una aplicación con ese identificador.')))
    const wrapper = await mountSuspended(ApplicationsFormModal, { props: { open: true }, attachTo: document.body })
    await fill(['mi-app', 'Mi app', '', 'https://m.test', ''])
    await submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ya existe una aplicación con ese identificador.'))
    expect(wrapper.emitted('created')).toBeUndefined()
  })

  it('error de red: mensaje legible, no el crudo', async () => {
    api.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')))
    await mountSuspended(ApplicationsFormModal, { props: { open: true }, attachTo: document.body })
    await fill(['mi-app', 'Mi app', '', 'https://m.test', ''])
    await submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('No se pudo conectar'))
    expect(document.body.textContent).not.toMatch(/failed to fetch/i)
  })

  it('editar: el slug va bloqueado y el PATCH no lo incluye', async () => {
    const application = { ...created.application, redirect_uris: ['https://m.test/cb'] }
    api.mockResolvedValue({ ...application, name: 'Nuevo nombre' })
    const wrapper = await mountSuspended(ApplicationsFormModal, { props: { open: true, application }, attachTo: document.body })
    const els = inputs()
    expect(els[0]!.disabled).toBe(true)
    expect(els[0]!.value).toBe('mi-app')
    expect(els[4]!.value).toBe('https://m.test/cb')
    await fill(['mi-app', 'Nuevo nombre', '', 'https://m.test', 'https://m.test/cb'])
    await submit()
    await vi.waitFor(() => expect(api).toHaveBeenCalled())
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/applications/a1', {
      method: 'PATCH',
      body: { name: 'Nuevo nombre', description: null, base_url: 'https://m.test', redirect_uris: ['https://m.test/cb'] }
    })
    expect(wrapper.emitted('updated')).toHaveLength(1)
  })
})
