import { describe, expect, it } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { roleErrorMessage } from './roleErrors'

describe('roleErrorMessage', () => {
  it('invalid_reference: explica que hay permisos que ya no están disponibles', () => {
    const err = new LeoApiError(422, 'invalid_reference', 'Algunas acciones no existen o no son de la aplicación del rol.', { action_ids: ['x'] })
    expect(roleErrorMessage(err)).toContain('Algunos permisos ya no están disponibles')
  })

  it('conflicto o 404: el mensaje del backend', () => {
    expect(roleErrorMessage(new LeoApiError(409, 'duplicate', 'Ya existe un rol en esta aplicación con el slug «x».'))).toBe('Ya existe un rol en esta aplicación con el slug «x».')
    expect(roleErrorMessage(new LeoApiError(404, 'not_found', 'No se encontró el rol.'))).toBe('No se encontró el rol.')
  })

  it('red o 500: legible, nunca crudo', () => {
    expect(roleErrorMessage(new TypeError('Failed to fetch'))).not.toMatch(/fetch/i)
    expect(roleErrorMessage(new LeoApiError(500, 'internal_error', 'Traceback (most recent call last)'))).not.toMatch(/traceback/i)
  })
})
