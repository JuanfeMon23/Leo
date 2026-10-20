import { describe, expect, it } from 'vitest'
import { LeoApiError } from '../../../../../client/app/lib/errors'
import { mapApiErrorToForm } from '#andromeda/utils/mapApiErrorToForm'
import { userErrorMessage } from './userErrors'

describe('userErrorMessage', () => {
  it('self_deactivation: texto propio y claro', () => {
    const err = new LeoApiError(409, 'self_deactivation', 'No puedes desactivar tu propio usuario.')
    expect(userErrorMessage(err)).toMatch(/propio usuario/i)
    expect(userErrorMessage(err)).toMatch(/otra persona|otro administrador/i)
  })

  it('weak_password: lista lo que falta sin mostrar la respuesta cruda', () => {
    const err = new LeoApiError(422, 'weak_password', 'La contraseña es débil: debe incluir un símbolo.', { password: ['debe incluir un símbolo'] })
    expect(userErrorMessage(err)).toContain('débil')
  })

  it('invalid_reference: rol que ya no existe o de otra aplicación', () => {
    const err = new LeoApiError(422, 'invalid_reference', 'x')
    expect(userErrorMessage(err)).toMatch(/rol/i)
  })

  it('el resto pasa por el mensaje legible del backend o el genérico', () => {
    expect(userErrorMessage(new LeoApiError(404, 'not_found', "No existe un usuario con id 'x'."))).toContain('No existe un usuario')
    expect(userErrorMessage(new TypeError('Failed to fetch'))).toMatch(/conectar/i)
    expect(userErrorMessage(new LeoApiError(500, 'internal_error', 'Traceback…'))).not.toContain('Traceback')
  })
})

describe('mapeo de errores del backend a campos (mapApiErrorToForm)', () => {
  const fields = ['username', 'email', 'document_number', 'password']

  it('correo duplicado → campo email, mensaje legible', () => {
    const err = new LeoApiError(409, 'duplicate', 'Ya existe un usuario con el email «a@x.co».', { email: 'a@x.co' })
    const r = mapApiErrorToForm(err, { fields })
    expect(r.fieldErrors.email).toContain('Ya existe un usuario con el email')
    expect(r.formError).toBeNull()
  })

  it('documento duplicado → campo document_number', () => {
    const err = new LeoApiError(409, 'duplicate', 'Ya existe un usuario con el documento «CC 123».', { document_number: 'CC 123' })
    expect(mapApiErrorToForm(err, { fields }).fieldErrors.document_number).toContain('documento')
  })

  it('weak_password → campo password', () => {
    const err = new LeoApiError(422, 'weak_password', 'La contraseña es débil: debe incluir un símbolo.', { password: ['debe incluir un símbolo'] })
    expect(mapApiErrorToForm(err, { fields }).fieldErrors.password).toContain('débil')
  })
})
