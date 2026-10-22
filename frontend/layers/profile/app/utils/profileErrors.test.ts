import { describe, expect, it } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { mapApiErrorToForm } from '#andromeda/utils/mapApiErrorToForm'
import { profilePasswordErrors } from './profileErrors'

describe('profilePasswordErrors', () => {
  it('invalid_credentials: error del campo «contraseña actual», sin error general', () => {
    const err = new LeoApiError(401, 'invalid_credentials', 'La contraseña actual no es correcta.')
    expect(profilePasswordErrors(err)).toEqual({ fields: { current_password: 'La contraseña actual no es correcta.' }, form: null })
  })

  it('weak_password: campo nuevo, con los requisitos incumplidos en minúscula', () => {
    const err = new LeoApiError(422, 'weak_password', 'Contraseña débil.', { password: ['Una letra mayúscula', 'Un número'] })
    const r = profilePasswordErrors(err)
    expect(r.form).toBeNull()
    expect(r.fields.new_password).toBe('La contraseña no cumple la política: una letra mayúscula; un número.')
  })

  it('weak_password sin detalle: mensaje genérico legible', () => {
    const err = new LeoApiError(422, 'weak_password', '', null)
    expect(profilePasswordErrors(err).fields.new_password).toMatch(/débil/)
  })

  it('same_password: campo nuevo', () => {
    const err = new LeoApiError(422, 'same_password', 'x')
    expect(profilePasswordErrors(err).fields.new_password).toMatch(/distinta de la actual/)
  })

  it('429 con Retry-After: espera legible', () => {
    const err = new LeoApiError(429, 'too_many_attempts', 'x', null, 120)
    expect(profilePasswordErrors(err).form).toBe('Demasiados intentos. Inténtalo de nuevo en 2 minutos.')
  })

  it('429 sin Retry-After: mensaje genérico', () => {
    expect(profilePasswordErrors(new LeoApiError(429, 'too_many_attempts', 'x')).form).toMatch(/Espera unos minutos/)
  })

  it('error de red o desconocido: mensaje legible, no el crudo', () => {
    const r = profilePasswordErrors(new TypeError('Failed to fetch'))
    expect(r.fields).toEqual({})
    expect(r.form).toBeTruthy()
    expect(r.form).not.toMatch(/failed to fetch/i)
  })
})

describe('errores del perfil con mapApiErrorToForm', () => {
  const fields = ['first_name', 'last_name', 'email']

  it('409 duplicate con details.email: mensaje en el campo del correo', () => {
    const err = new LeoApiError(409, 'duplicate', 'Ya existe un usuario con el email «a@x.co».', { email: 'a@x.co' })
    const r = mapApiErrorToForm(err, { fields })
    expect(r.formError).toBeNull()
    expect(r.fieldErrors.email).toContain('Ya existe un usuario con el email')
  })

  it('422 validation_error con details [{field,message}]: cada campo con su mensaje', () => {
    const err = new LeoApiError(422, 'validation_error', 'Datos inválidos.', [
      { field: 'body.first_name', message: 'Demasiado largo.' },
      { field: 'body.email', message: 'Correo inválido.' }
    ])
    const r = mapApiErrorToForm(err, { fields })
    expect(r.formError).toBeNull()
    expect(r.fieldErrors).toEqual({ first_name: 'Demasiado largo.', email: 'Correo inválido.' })
  })
})
