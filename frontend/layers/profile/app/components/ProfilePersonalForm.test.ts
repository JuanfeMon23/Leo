import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { enableAutoUnmount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { signInWith } from '../../../../tests/helpers/session'
import ProfilePersonalForm from './ProfilePersonalForm.vue'

enableAutoUnmount(afterEach)

const { api } = vi.hoisted(() => ({ api: vi.fn() }))
mockNuxtImport('useLeoApi', () => () => api)

const ME = (first = 'Ana', last = 'Pérez', email = 'a@x.co') => ({
  user: { id: 'u1', username: 'ana', email, first_name: first, last_name: last },
  session: { id: 's', expires_at: '', last_activity_at: '', idle_timeout_seconds: 0 },
  permissions: [],
  applications: []
})

type Attr = { attributes: (name: string) => string | undefined }
type El = { element: HTMLInputElement }
type Wrapper = Awaited<ReturnType<typeof mountSuspended>>
const inputs = (wrapper: Wrapper) => wrapper.findAll('input')
const save = (wrapper: Wrapper) => wrapper.get('[data-testid="profile-save"]')
const submit = async (wrapper: Wrapper) => {
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

beforeEach(() => {
  api.mockReset()
  signInWith([]) // usuario ana / Ana Pérez / a@x.co
})

describe('ProfilePersonalForm', () => {
  it('muestra el usuario (solo lectura) y los datos actuales', async () => {
    const wrapper = await mountSuspended(ProfilePersonalForm)
    expect(wrapper.get('[data-testid="profile-username"]').text()).toContain('ana')
    expect(inputs(wrapper).map((i: El) => i.element.value)).toEqual(['Ana', 'Pérez', 'a@x.co'])
    expect(wrapper.text()).not.toMatch(/documento/i)
  })

  it('«Guardar cambios» está deshabilitado sin cambios y se habilita al editar', async () => {
    const wrapper = await mountSuspended(ProfilePersonalForm)
    expect(save(wrapper).attributes('disabled')).toBeDefined()
    await inputs(wrapper)[0]!.setValue('Ana María')
    expect(save(wrapper).attributes('disabled')).toBeUndefined()
    await inputs(wrapper)[0]!.setValue('  Ana  ') // solo espacios: sigue sin cambios
    expect(save(wrapper).attributes('disabled')).toBeDefined()
  })

  it('campos inválidos: errores de zod y no llama a la API', async () => {
    const wrapper = await mountSuspended(ProfilePersonalForm)
    await inputs(wrapper)[0]!.setValue('   ')
    await inputs(wrapper)[2]!.setValue('sin-arroba')
    await submit(wrapper)
    await vi.waitFor(() => expect(wrapper.text()).toContain('Los nombres son obligatorios.'))
    expect(wrapper.text()).toContain('Ingresa un correo electrónico válido.')
    expect(api).not.toHaveBeenCalled()
  })

  it('éxito: envía solo lo que cambió, actualiza el estado de sesión y avisa', async () => {
    api.mockResolvedValue(ME('Ana María'))
    const wrapper = await mountSuspended(ProfilePersonalForm)
    await inputs(wrapper)[0]!.setValue(' Ana María ')
    await submit(wrapper)
    await vi.waitFor(() => expect(api).toHaveBeenCalled())
    expect(api).toHaveBeenCalledWith('/auth/me/profile', { method: 'PATCH', body: { first_name: 'Ana María' } })
    await flushPromises()
    expect(useState<{ me: ReturnType<typeof ME> }>('leo-session').value.me.user.first_name).toBe('Ana María')
    expect(useToast().toasts.value.map(toast => toast.message)).toContain('Datos actualizados')
    expect(save(wrapper).attributes('disabled')).toBeDefined() // ya no hay cambios pendientes
  })

  it('correo duplicado (409): mensaje en el campo del correo', async () => {
    api.mockRejectedValue(new LeoApiError(409, 'duplicate', 'Ya existe un usuario con el email «b@x.co».', { email: 'b@x.co' }))
    const wrapper = await mountSuspended(ProfilePersonalForm)
    await inputs(wrapper)[2]!.setValue('b@x.co')
    await wrapper.get('input[autocomplete="current-password"]').setValue('Secreta-123')
    await submit(wrapper)
    await vi.waitFor(() => expect(wrapper.text()).toContain('Ya existe un usuario con el email'))
    expect(wrapper.find('[data-testid="profile-error"]').exists()).toBe(false)
    expect(useState<{ me: ReturnType<typeof ME> }>('leo-session').value.me.user.email).toBe('a@x.co')
  })

  it('error de red: mensaje legible, no el crudo', async () => {
    api.mockRejectedValue(new TypeError('Failed to fetch'))
    const wrapper = await mountSuspended(ProfilePersonalForm)
    await inputs(wrapper)[1]!.setValue('Gómez')
    await submit(wrapper)
    await vi.waitFor(() => expect(wrapper.find('[data-testid="profile-error"]').exists()).toBe(true))
    expect(wrapper.text()).not.toMatch(/failed to fetch/i)
  })

  describe('cambio de correo', () => {
    const pwd = (wrapper: Wrapper) => wrapper.find('input[autocomplete="current-password"]')

    it('el campo «Contraseña actual» solo aparece si el correo cambia', async () => {
      const wrapper = await mountSuspended(ProfilePersonalForm)
      expect(pwd(wrapper).exists()).toBe(false)
      await inputs(wrapper)[2]!.setValue('nuevo@x.co')
      expect(pwd(wrapper).exists()).toBe(true)
      await inputs(wrapper)[2]!.setValue('a@x.co')
      expect(pwd(wrapper).exists()).toBe(false)
    })

    it('sin contraseña actual: error en el campo y no llama a la API', async () => {
      const wrapper = await mountSuspended(ProfilePersonalForm)
      await inputs(wrapper)[2]!.setValue('nuevo@x.co')
      await submit(wrapper)
      await vi.waitFor(() => expect(wrapper.text()).toContain('Ingresa tu contraseña actual'))
      expect(api).not.toHaveBeenCalled()
    })

    it('envía current_password con el correo y limpia el campo al guardar', async () => {
      api.mockResolvedValue(ME('Ana', 'Pérez', 'nuevo@x.co'))
      const wrapper = await mountSuspended(ProfilePersonalForm)
      await inputs(wrapper)[2]!.setValue('nuevo@x.co')
      await pwd(wrapper).setValue('Secreta-123')
      await submit(wrapper)
      await vi.waitFor(() => expect(api).toHaveBeenCalled())
      expect(api).toHaveBeenCalledWith('/auth/me/profile', { method: 'PATCH', body: { email: 'nuevo@x.co', current_password: 'Secreta-123' } })
      await flushPromises()
      expect(pwd(wrapper).exists()).toBe(false)
    })

    it('sin cambiar el correo no manda current_password', async () => {
      api.mockResolvedValue(ME('Ana María'))
      const wrapper = await mountSuspended(ProfilePersonalForm)
      await inputs(wrapper)[0]!.setValue('Ana María')
      await submit(wrapper)
      await vi.waitFor(() => expect(api).toHaveBeenCalled())
      expect(api.mock.calls[0]![1].body).not.toHaveProperty('current_password')
    })

    it('invalid_current_password (403): mensaje legible en el campo y se vacía', async () => {
      api.mockRejectedValue(new LeoApiError(403, 'invalid_current_password', 'raw backend'))
      const wrapper = await mountSuspended(ProfilePersonalForm)
      await inputs(wrapper)[2]!.setValue('nuevo@x.co')
      await pwd(wrapper).setValue('mala')
      await submit(wrapper)
      await vi.waitFor(() => expect(wrapper.text()).toContain('La contraseña actual no es correcta.'))
      expect(wrapper.text()).not.toContain('raw backend')
      expect((pwd(wrapper).element as HTMLInputElement).value).toBe('')
    })

    it('current_password_required (422): mensaje en el campo', async () => {
      api.mockRejectedValue(new LeoApiError(422, 'current_password_required', 'raw'))
      const wrapper = await mountSuspended(ProfilePersonalForm)
      await inputs(wrapper)[2]!.setValue('nuevo@x.co')
      await pwd(wrapper).setValue('x')
      await submit(wrapper)
      await vi.waitFor(() => expect(wrapper.text()).toContain('Ingresa tu contraseña actual'))
    })
  })
})
