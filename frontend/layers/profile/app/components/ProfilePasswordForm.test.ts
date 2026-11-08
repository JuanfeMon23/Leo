import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { signInWith } from '../../../../tests/helpers/session'
import { clearPasswordPolicyCache } from '../../../../app/composables/usePasswordPolicy'
import ProfilePasswordForm from './ProfilePasswordForm.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const OLD = 'Vieja-Clave-2025'
const NEW = 'Segura-Clave-2026'

type Attr = { attributes: (name: string) => string | undefined }
type El = { element: HTMLInputElement }
type Wrapper = Awaited<ReturnType<typeof mountSuspended>>
const inputs = (wrapper: Wrapper) => wrapper.findAll('input')
// Llamadas distintas de la lectura de la política de contraseña.
const writes = () => api.mock.calls.filter(call => call[0] !== '/auth/password-policy')
const dialog = () => document.body.querySelector('[role="dialog"]')
const reqs = (wrapper: Wrapper) => wrapper.findAll('[data-testid="password-requirement"]').map((item: Attr) => item.attributes('data-met'))

async function fill(wrapper: Wrapper, current = OLD, next = NEW, confirm = next) {
  await inputs(wrapper)[0]!.setValue(current)
  await inputs(wrapper)[1]!.setValue(next)
  await inputs(wrapper)[2]!.setValue(confirm)
}
async function submit(wrapper: Wrapper) {
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}
async function confirmDialog() {
  await vi.waitFor(() => expect(dialog()).not.toBeNull())
  const buttons = [...dialog()!.querySelectorAll('button')]
  buttons.find(button => button.textContent?.includes('Cambiar contraseña'))!.click()
  await flushPromises()
}

beforeEach(() => {
  api.mockReset()
  clearPasswordPolicyCache()
  signInWith([]) // usuario ana, correo a@x.co
})
afterEach(() => { document.body.innerHTML = '' })

describe('ProfilePasswordForm', () => {
  it('los campos son de tipo contraseña y los requisitos se actualizan en vivo', async () => {
    const wrapper = await mountSuspended(ProfilePasswordForm)
    expect(inputs(wrapper).map((i: Attr) => i.attributes('type'))).toEqual(['password', 'password', 'password'])
    expect(reqs(wrapper)).toEqual(['false', 'false', 'false', 'false', 'false'])
    await inputs(wrapper)[1]!.setValue(NEW)
    expect(reqs(wrapper)).toEqual(['true', 'true', 'true', 'true', 'true'])
    await inputs(wrapper)[1]!.setValue('Hola-ana-2026!') // contiene el usuario: ya no se penaliza
    expect(reqs(wrapper)).toEqual(['true', 'true', 'true', 'true', 'true'])
    expect(wrapper.text()).not.toContain('Hola-ana-2026!') // solo vive en el campo
  })

  it('muestra y aplica la política que publica el servidor', async () => {
    api.mockResolvedValue({
      min_length: 6, max_length: 64, require_lowercase: true, require_uppercase: false, require_digit: false, require_symbol: false
    })
    const wrapper = await mountSuspended(ProfilePasswordForm)
    await vi.waitFor(() => expect(reqs(wrapper)).toHaveLength(2))
    expect(api).toHaveBeenCalledWith('/auth/password-policy', { skipSessionHandling: true })
    await inputs(wrapper)[1]!.setValue('minuscula')
    expect(reqs(wrapper)).toEqual(['true', 'true'])
  })

  it('débil, igual a la actual o sin coincidir: errores y no se pide confirmación ni se llama a la API', async () => {
    const wrapper = await mountSuspended(ProfilePasswordForm)
    await fill(wrapper, OLD, 'corta', 'otra')
    await submit(wrapper)
    await vi.waitFor(() => expect(wrapper.text()).toContain('aún no cumple todos los requisitos'))
    expect(wrapper.text()).toContain('Las contraseñas no coinciden.')
    await fill(wrapper, NEW, NEW)
    await submit(wrapper)
    await vi.waitFor(() => expect(wrapper.text()).toContain('distinta de la actual'))
    expect(writes()).toEqual([])
    expect(dialog()).toBeNull()
  })

  it('pide confirmación advirtiendo que se cierran las demás sesiones, y no envía hasta confirmar', async () => {
    const wrapper = await mountSuspended(ProfilePasswordForm)
    await fill(wrapper)
    await submit(wrapper)
    await vi.waitFor(() => expect(dialog()).not.toBeNull())
    expect(dialog()!.textContent).toContain('demás sesiones')
    expect(writes()).toEqual([])
  })

  it('éxito: envía las contraseñas, avisa, limpia el formulario y mantiene la sesión', async () => {
    api.mockResolvedValue(undefined)
    const wrapper = await mountSuspended(ProfilePasswordForm)
    await fill(wrapper)
    await submit(wrapper)
    await confirmDialog()
    expect(api).toHaveBeenCalledWith('/auth/me/password', {
      method: 'POST',
      body: { current_password: OLD, new_password: NEW },
      skipSessionHandling: true
    })
    await vi.waitFor(() => expect(wrapper.find('[data-testid="password-success"]').exists()).toBe(true))
    expect(wrapper.get('[data-testid="password-success"]').text()).toContain('Contraseña actualizada. Se cerraron tus otras sesiones.')
    expect(inputs(wrapper).map((i: El) => i.element.value)).toEqual(['', '', ''])
    expect(useState<{ status: string }>('leo-session').value.status).toBe('authenticated')
    expect(wrapper.text()).not.toContain(NEW)
  })

  it('contraseña actual incorrecta (401 invalid_credentials): error del campo, se limpia y la sesión sigue', async () => {
    api.mockRejectedValue(new LeoApiError(401, 'invalid_credentials', 'La contraseña actual no es correcta.'))
    const wrapper = await mountSuspended(ProfilePasswordForm)
    await fill(wrapper)
    await submit(wrapper)
    await confirmDialog()
    await vi.waitFor(() => expect(wrapper.text()).toContain('La contraseña actual no es correcta.'))
    expect(inputs(wrapper)[0]!.element.value).toBe('')
    expect(useState<{ status: string }>('leo-session').value.status).toBe('authenticated')
    expect(wrapper.find('[data-testid="password-success"]').exists()).toBe(false)
  })

  it('weak_password (422): requisitos incumplidos en el campo nuevo', async () => {
    api.mockRejectedValue(new LeoApiError(422, 'weak_password', 'x', { password: ['Un símbolo'] }))
    const wrapper = await mountSuspended(ProfilePasswordForm)
    await fill(wrapper)
    await submit(wrapper)
    await confirmDialog()
    await vi.waitFor(() => expect(wrapper.text()).toContain('no cumple la política: un símbolo'))
  })

  it('same_password (422): mensaje en el campo nuevo', async () => {
    api.mockRejectedValue(new LeoApiError(422, 'same_password', 'x'))
    const wrapper = await mountSuspended(ProfilePasswordForm)
    await fill(wrapper)
    await submit(wrapper)
    await confirmDialog()
    await vi.waitFor(() => expect(wrapper.text()).toContain('distinta de la actual'))
  })

  it('429: error general con la espera', async () => {
    api.mockRejectedValue(new LeoApiError(429, 'too_many_attempts', 'x', null, 90))
    const wrapper = await mountSuspended(ProfilePasswordForm)
    await fill(wrapper)
    await submit(wrapper)
    await confirmDialog()
    await vi.waitFor(() => expect(wrapper.get('[data-testid="password-error"]').text()).toContain('en 2 minutos'))
  })

  it('error de red: mensaje legible, no el crudo', async () => {
    api.mockRejectedValue(new TypeError('Failed to fetch'))
    const wrapper = await mountSuspended(ProfilePasswordForm)
    await fill(wrapper)
    await submit(wrapper)
    await confirmDialog()
    await vi.waitFor(() => expect(wrapper.find('[data-testid="password-error"]').exists()).toBe(true))
    expect(wrapper.text()).not.toMatch(/failed to fetch/i)
  })
})
