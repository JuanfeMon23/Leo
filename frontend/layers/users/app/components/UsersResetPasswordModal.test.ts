import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { ALL_USERS_TAGS, signInWith } from '../../../../tests/helpers/session'
import UsersResetPasswordModal from './UsersResetPasswordModal.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const user = {
  id: 'u2', username: 'luis', email: 'luis@x.co', document_type: 'CC', document_number: '1', first_name: 'Luis', last_name: 'Mora',
  is_active: true, last_login_at: null, failed_login_attempts: 0, locked_until: null, created_at: '', updated_at: ''
} as never

beforeEach(() => {
  api.mockReset()
  signInWith(ALL_USERS_TAGS)
})
afterEach(() => { document.body.innerHTML = '' })

const dialog = () => document.body.querySelector('[role="dialog"]')!
const field = () => dialog().querySelector<HTMLInputElement>('input[type="password"]')!
async function type(value: string) {
  field().value = value
  field().dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
const submit = () => dialog().querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit', { cancelable: true }))

describe('UsersResetPasswordModal', () => {
  it('advierte que cierra todas las sesiones del usuario', async () => {
    await mountSuspended(UsersResetPasswordModal, { props: { open: true, user }, attachTo: document.body })
    expect(dialog().querySelector('[data-testid="reset-warning"]')!.textContent).toMatch(/cerrarán todas las sesiones/)
  })

  it('contraseña que contiene el usuario: ya se acepta y llama a la API', async () => {
    api.mockResolvedValue(user)
    await mountSuspended(UsersResetPasswordModal, { props: { open: true, user }, attachTo: document.body })
    await type('Clave-luis-2026!')
    submit()
    await vi.waitFor(() => expect(api).toHaveBeenCalled())
    expect(api).toHaveBeenCalledWith('/users/u2/reset-password', { method: 'POST', body: { password: 'Clave-luis-2026!' } })
  })

  it('contraseña válida: POST reset-password con solo la contraseña y avisa', async () => {
    api.mockResolvedValue(user)
    const wrapper = await mountSuspended(UsersResetPasswordModal, { props: { open: true, user }, attachTo: document.body })
    await type('Segura-Clave-2026')
    submit()
    await vi.waitFor(() => expect(api).toHaveBeenCalled())
    await flushPromises()
    expect(api).toHaveBeenCalledWith('/users/u2/reset-password', { method: 'POST', body: { password: 'Segura-Clave-2026' } })
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('weak_password del backend: mensaje en el campo', async () => {
    api.mockRejectedValue(new LeoApiError(422, 'weak_password', 'La contraseña es débil: debe incluir un símbolo.', { password: ['debe incluir un símbolo'] }))
    await mountSuspended(UsersResetPasswordModal, { props: { open: true, user }, attachTo: document.body })
    await type('Segura-Clave-2026')
    submit()
    await vi.waitFor(() => expect(document.body.textContent).toContain('La contraseña es débil'))
  })
})
