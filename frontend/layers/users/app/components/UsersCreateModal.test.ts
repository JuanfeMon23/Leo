import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_USERS_TAGS, signInWith } from '../../../../tests/helpers/session'
import UsersCreateModal from './UsersCreateModal.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const saved = { id: 'u9', username: 'ana.perez' }

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_USERS_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

const dialog = () => document.body.querySelector('[role="dialog"]')!
const input = (name: string) => dialog().querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"], #field-${name}`)
const controls = () => [...dialog().querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select')]
async function type(el: HTMLInputElement | HTMLSelectElement, value: string) {
  el.value = value
  el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }))
  await flushPromises()
}
const submit = () => dialog().querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit', { cancelable: true }))

/** Orden de los controles: usuario, nombres, apellidos, correo, tipo doc, número doc, contraseña. */
async function fill(over: Partial<Record<'username' | 'first' | 'last' | 'email' | 'type' | 'number' | 'password', string>> = {}) {
  const v = { username: 'ana.perez', first: 'Ana', last: 'Pérez', email: 'ana@x.co', type: 'CC', number: '1.234', password: 'Segura-Clave-2026', ...over }
  const c = controls()
  await type(c[0]!, v.username)
  await type(c[1]!, v.first)
  await type(c[2]!, v.last)
  await type(c[3]!, v.email)
  await type(c[4]!, v.type)
  await type(c[5]!, v.number)
  await type(c[6]!, v.password)
}

describe('UsersCreateModal', () => {
  it('muestra los requisitos de la contraseña y se actualizan al escribir', async () => {
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    const reqs = () => [...dialog().querySelectorAll('[data-testid="password-requirement"]')].map(li => li.getAttribute('data-met'))
    expect(reqs()).toEqual(['false', 'false', 'false', 'false', 'false'])
    await type(controls()[6]!, 'Segura-Clave-2026')
    expect(reqs()).toEqual(['true', 'true', 'true', 'true', 'true'])
  })

  it('un documento con puntos y una contraseña débil no llaman a la API', async () => {
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await fill({ number: '1.234.567', password: 'corta' })
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('sin puntos ni espacios'))
    expect(document.body.textContent).toContain('Falta:')
    expect(api).not.toHaveBeenCalled()
  })

  it('el número de documento con letras se envía en mayúsculas y el usuario en minúsculas', async () => {
    api.mockResolvedValue(saved)
    const wrapper = await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await fill({ username: 'Ana.Perez', number: 'ab-12' })
    submit()
    await vi.waitFor(() => expect(api).toHaveBeenCalled())
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
    api.mockRejectedValue(new LeoApiError(409, 'duplicate', 'Ya existe un usuario con el email «ana@x.co».', { email: 'ana@x.co' }))
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await fill({ number: '1234' })
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ya existe un usuario con el email'))
  })

  it('documento duplicado (409): mensaje en el campo del documento', async () => {
    api.mockRejectedValue(new LeoApiError(409, 'duplicate', 'Ya existe un usuario con el documento «CC 1234».', { document_number: 'CC 1234' }))
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await fill({ number: '1234' })
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ya existe un usuario con el documento'))
  })

  it('error de red: mensaje legible, no el crudo', async () => {
    api.mockRejectedValue(new TypeError('Failed to fetch'))
    await mountSuspended(UsersCreateModal, { props: { open: true }, attachTo: document.body })
    await fill({ number: '1234' })
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('No se pudo conectar'))
    expect(document.body.textContent).not.toMatch(/failed to fetch/i)
  })

  it('al cerrar se limpia la contraseña', async () => {
    const wrapper = await mountSuspended(UsersCreateModal, { props: { open: true, 'onUpdate:open': (v: boolean) => wrapper.setProps({ open: v }) }, attachTo: document.body })
    await type(controls()[6]!, 'Segura-Clave-2026')
    await wrapper.setProps({ open: false })
    await flushPromises()
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(controls()[6]!.value).toBe('')
  })
})
