import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { signInWith } from '../../../../tests/helpers/session'
import ProfilePasswordForm from './ProfilePasswordForm.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const OLD = 'Vieja-Clave-2025'
const NEW = 'Segura-Clave-2026'

type Attr = { attributes: (name: string) => string | undefined }
type El = { element: HTMLInputElement }
type Wrapper = Awaited<ReturnType<typeof mountSuspended>>
const inputs = (w: Wrapper) => w.findAll('input')
const dialog = () => document.body.querySelector('[role="dialog"]')
const reqs = (w: Wrapper) => w.findAll('[data-testid="password-requirement"]').map((li: Attr) => li.attributes('data-met'))

async function fill(w: Wrapper, current = OLD, next = NEW, confirm = next) {
  await inputs(w)[0]!.setValue(current)
  await inputs(w)[1]!.setValue(next)
  await inputs(w)[2]!.setValue(confirm)
}
async function submit(w: Wrapper) {
  await w.get('form').trigger('submit')
  await flushPromises()
}
async function confirmDialog() {
  await vi.waitFor(() => expect(dialog()).not.toBeNull())
  const buttons = [...dialog()!.querySelectorAll('button')]
  buttons.find(b => b.textContent?.includes('Cambiar contraseña'))!.click()
  await flushPromises()
}

beforeEach(() => {
  api.mockReset()
  signInWith([]) // usuario ana, correo a@x.co
})
afterEach(() => { document.body.innerHTML = '' })

describe('ProfilePasswordForm', () => {
  it('los campos son de tipo contraseña y los requisitos se actualizan en vivo', async () => {
    const w = await mountSuspended(ProfilePasswordForm)
    expect(inputs(w).map((i: Attr) => i.attributes('type'))).toEqual(['password', 'password', 'password'])
    expect(reqs(w)).toEqual(['false', 'false', 'false', 'false', 'false'])
    await inputs(w)[1]!.setValue(NEW)
    expect(reqs(w)).toEqual(['true', 'true', 'true', 'true', 'true'])
    await inputs(w)[1]!.setValue('Hola-ana-2026!') // contiene el usuario: ya no se penaliza
    expect(reqs(w)).toEqual(['true', 'true', 'true', 'true', 'true'])
    expect(w.text()).not.toContain('Hola-ana-2026!') // solo vive en el campo
  })

  it('débil, igual a la actual o sin coincidir: errores y no se pide confirmación ni se llama a la API', async () => {
    const w = await mountSuspended(ProfilePasswordForm)
    await fill(w, OLD, 'corta', 'otra')
    await submit(w)
    await vi.waitFor(() => expect(w.text()).toContain('Falta:'))
    expect(w.text()).toContain('Las contraseñas no coinciden.')
    await fill(w, NEW, NEW)
    await submit(w)
    await vi.waitFor(() => expect(w.text()).toContain('distinta de la actual'))
    expect(api).not.toHaveBeenCalled()
    expect(dialog()).toBeNull()
  })

  it('pide confirmación advirtiendo que se cierran las demás sesiones, y no envía hasta confirmar', async () => {
    const w = await mountSuspended(ProfilePasswordForm)
    await fill(w)
    await submit(w)
    await vi.waitFor(() => expect(dialog()).not.toBeNull())
    expect(dialog()!.textContent).toContain('demás sesiones')
    expect(api).not.toHaveBeenCalled()
  })

  it('éxito: envía las contraseñas, avisa, limpia el formulario y mantiene la sesión', async () => {
    api.mockResolvedValue(undefined)
    const w = await mountSuspended(ProfilePasswordForm)
    await fill(w)
    await submit(w)
    await confirmDialog()
    expect(api).toHaveBeenCalledWith('/auth/me/password', {
      method: 'POST',
      body: { current_password: OLD, new_password: NEW },
      skipSessionHandling: true
    })
    await vi.waitFor(() => expect(w.find('[data-testid="password-success"]').exists()).toBe(true))
    expect(w.get('[data-testid="password-success"]').text()).toContain('Contraseña actualizada. Se cerraron tus otras sesiones.')
    expect(inputs(w).map((i: El) => i.element.value)).toEqual(['', '', ''])
    expect(useState<{ status: string }>('leo-session').value.status).toBe('authenticated')
    expect(w.text()).not.toContain(NEW)
  })

  it('contraseña actual incorrecta (401 invalid_credentials): error del campo, se limpia y la sesión sigue', async () => {
    api.mockRejectedValue(new LeoApiError(401, 'invalid_credentials', 'La contraseña actual no es correcta.'))
    const w = await mountSuspended(ProfilePasswordForm)
    await fill(w)
    await submit(w)
    await confirmDialog()
    await vi.waitFor(() => expect(w.text()).toContain('La contraseña actual no es correcta.'))
    expect(inputs(w)[0]!.element.value).toBe('')
    expect(useState<{ status: string }>('leo-session').value.status).toBe('authenticated')
    expect(w.find('[data-testid="password-success"]').exists()).toBe(false)
  })

  it('weak_password (422): requisitos incumplidos en el campo nuevo', async () => {
    api.mockRejectedValue(new LeoApiError(422, 'weak_password', 'x', { password: ['Un símbolo'] }))
    const w = await mountSuspended(ProfilePasswordForm)
    await fill(w)
    await submit(w)
    await confirmDialog()
    await vi.waitFor(() => expect(w.text()).toContain('no cumple la política: un símbolo'))
  })

  it('same_password (422): mensaje en el campo nuevo', async () => {
    api.mockRejectedValue(new LeoApiError(422, 'same_password', 'x'))
    const w = await mountSuspended(ProfilePasswordForm)
    await fill(w)
    await submit(w)
    await confirmDialog()
    await vi.waitFor(() => expect(w.text()).toContain('distinta de la actual'))
  })

  it('429: error general con la espera', async () => {
    api.mockRejectedValue(new LeoApiError(429, 'too_many_attempts', 'x', null, 90))
    const w = await mountSuspended(ProfilePasswordForm)
    await fill(w)
    await submit(w)
    await confirmDialog()
    await vi.waitFor(() => expect(w.get('[data-testid="password-error"]').text()).toContain('en 2 minutos'))
  })

  it('error de red: mensaje legible, no el crudo', async () => {
    api.mockRejectedValue(new TypeError('Failed to fetch'))
    const w = await mountSuspended(ProfilePasswordForm)
    await fill(w)
    await submit(w)
    await confirmDialog()
    await vi.waitFor(() => expect(w.find('[data-testid="password-error"]').exists()).toBe(true))
    expect(w.text()).not.toMatch(/failed to fetch/i)
  })
})
