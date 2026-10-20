import { describe, expect, it } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { applicationErrorMessage } from './applicationErrors'

describe('applicationErrorMessage', () => {
  it('leo_app_protected: explica que la app Leo es de solo lectura', () => {
    const err = new LeoApiError(409, 'leo_app_protected', 'texto del backend')
    expect(applicationErrorMessage(err)).toContain('Leo')
    expect(applicationErrorMessage(err)).toContain('no se puede modificar')
  })

  it('conflicto (409): el mensaje del backend', () => {
    const err = new LeoApiError(409, 'duplicate_value', 'Ya existe una aplicación con ese identificador.')
    expect(applicationErrorMessage(err)).toBe('Ya existe una aplicación con ese identificador.')
  })

  it('event_action_readonly: mensaje del backend, legible', () => {
    const err = new LeoApiError(409, 'event_action_readonly', '«leo.users.login» es una acción de evento (solo se audita): no se puede editar.', { tag: 'leo.users.login' })
    expect(applicationErrorMessage(err)).toBe('«leo.users.login» es una acción de evento (solo se audita): no se puede editar.')
  })

  it('403: el mensaje del backend', () => {
    expect(applicationErrorMessage(new LeoApiError(403, 'forbidden', 'No tienes acceso.'))).toBe('No tienes acceso.')
  })

  it('red o 500: legible, nunca crudo', () => {
    expect(applicationErrorMessage(new TypeError('Failed to fetch'))).not.toMatch(/fetch/i)
    expect(applicationErrorMessage(new LeoApiError(500, 'internal_error', 'Traceback (most recent call last)'))).not.toMatch(/traceback/i)
  })
})
