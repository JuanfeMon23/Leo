import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_USERS_TAGS, signInWith } from '../../../../tests/helpers/session'
import { clearPasswordPolicyCache } from '../../../../app/composables/usePasswordPolicy'
import { clearDocumentTypesCache } from '../../../../app/composables/useDocumentTypes'
import UsersCreateModal from './UsersCreateModal.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const saved = { id: 'u9', username: 'ana.perez' }
const TYPES = [
  { code: 'CC', name: 'Cédula de ciudadanía', sort_order: 10, is_active: true },
  { code: 'CE', name: 'Cédula de extranjería', sort_order: 20, is_active: true },
  { code: 'OLD', name: 'Tipo antiguo', sort_order: 99, is_active: false }
]

/** El catálogo responde siempre; `/users` responde `outcome` (valor o error). */
function respondUsers(outcome: unknown) {
  api.mockImplementation(async (url: string, options: { query: { active: boolean } }) => {
    if (url === '/document-types') return TYPES.filter(type => type.is_active === options.query.active)
    if (outcome instanceof Error) throw outcome
    return outcome
  })
}

beforeEach(() => {
  api.mockReset()
  clearPasswordPolicyCache()
  clearDocumentTypesCache()
  signInWith(ALL_USERS_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

const dialog = () => document.body.querySelector('[role="dialog"]')!
const input = (name: string) => dialog().querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"], #field-${name}`)
const controls = () => [...dialog().querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select')]
async function type(element: HTMLInputElement | HTMLSelectElement, value: string) {
  element.value = value
  element.dispatchEvent(new Event(element instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }))
  await flushPromises()
}
const submit = () => dialog().querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit', { cancelable: true }))

/** Orden de los controles: usuario, nombres, apellidos, correo, tipo doc, número doc, contraseña. */
async function fill(over: Partial<Record<'username' | 'first' | 'last' | 'email' | 'type' | 'number' | 'password', string>> = {}) {
  const values = { username: 'ana.perez', first: 'Ana', last: 'Pérez', email: 'ana@x.co', type: 'CC', number: '1.234', password: 'Segura-Clave-2026', ...over }
  const fields = controls()
  await type(fields[0]!, values.username)
  await type(fields[1]!, values.first)
  await type(fields[2]!, values.last)
  await type(fields[3]!, values.email)
  await type(fields[4]!, values.type)
  await type(fields[5]!, values.number)
  await type(fields[6]!, values.password)
}

describe('UsersCreateModal', () => {
  it('muestra los requisitos de la contraseña y se actualizan al escribir', async () => {
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    const reqs = () => [...dialog().querySelectorAll('[data-testid="password-requirement"]')].map(item => item.getAttribute('data-met'))
    expect(reqs()).toEqual(['false', 'false', 'false', 'false', 'false'])
    await type(controls()[6]!, 'Segura-Clave-2026')
    expect(reqs()).toEqual(['true', 'true', 'true', 'true', 'true'])
  })

  it('un documento con puntos y una contraseña débil no llaman a la API', async () => {
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await fill({ number: '1.234.567', password: 'corta' })
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('sin puntos ni espacios'))
    expect(document.body.textContent).toContain('aún no cumple todos los requisitos')
    expect(api.mock.calls.filter(call => !['/auth/password-policy', '/document-types'].includes(call[0]))).toEqual([])
  })

  it('el número de documento con letras se envía en mayúsculas y el usuario en minúsculas', async () => {
    respondUsers(saved)
    const wrapper = await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await fill({ username: 'Ana.Perez', number: 'ab-12' })
    submit()
    await vi.waitFor(() => expect(api).toHaveBeenCalledWith(expect.stringContaining('/users'), expect.anything()))
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/users', {
      method: 'POST',
      body: {
        username: 'ana.perez', email: 'ana@x.co', first_name: 'Ana', last_name: 'Pérez',
        document_type: 'CC', document_number: 'AB-12', password: 'Segura-Clave-2026'
      }
    })
    expect(wrapper.emitted('saved')?.[0]).toEqual([saved])
  })

  it('correo duplicado (409): mensaje legible en el campo del correo', async () => {
    respondUsers(new LeoApiError(409, 'duplicate', 'Ya existe un usuario con el email «ana@x.co».', { email: 'ana@x.co' }))
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await fill({ number: '1234' })
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ya existe un usuario con el email'))
  })

  it('documento duplicado (409): mensaje en el campo del documento', async () => {
    respondUsers(new LeoApiError(409, 'duplicate', 'Ya existe un usuario con el documento «CC 1234».', { document_number: 'CC 1234' }))
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await fill({ number: '1234' })
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ya existe un usuario con el documento'))
  })

  it('el selector ofrece solo los tipos activos del catálogo del servidor', async () => {
    respondUsers(saved)
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await vi.waitFor(() => expect(dialog().querySelectorAll('select option').length).toBeGreaterThan(1))
    const labels = [...dialog().querySelectorAll('select option')].map(option => option.textContent?.trim())
    expect(labels).toContain('CC · Cédula de ciudadanía')
    expect(labels).toContain('CE · Cédula de extranjería')
    expect(labels.join('|')).not.toContain('Tipo antiguo')
  })

  it('tipo de documento inválido (422 invalid_document_type): mensaje en el campo del tipo', async () => {
    respondUsers(new LeoApiError(422, 'invalid_document_type', 'El tipo de documento «XX» no existe o está inactivo.', { document_type: 'XX' }))
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await vi.waitFor(() => expect(dialog().querySelectorAll('select option').length).toBeGreaterThan(1))
    await fill({ number: '1234' })
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('ya no está disponible'))
    expect(document.body.textContent).not.toMatch(/invalid_document_type/)
  })

  it('error de red: mensaje legible, no el crudo', async () => {
    respondUsers(new TypeError('Failed to fetch'))
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await fill({ number: '1234' })
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('No se pudo conectar'))
    expect(document.body.textContent).not.toMatch(/failed to fetch/i)
  })

  it('al cerrar se limpia la contraseña', async () => {
    const wrapper = await mountSuspended(UsersCreateModal, { props: { open: true, 'onUpdate:open': (isOpen: boolean) => wrapper.setProps({ open: isOpen }) }, attachTo: document.body })
    await type(controls()[6]!, 'Segura-Clave-2026')
    await wrapper.setProps({ open: false })
    await flushPromises()
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(controls()[6]!.value).toBe('')
  })
})
