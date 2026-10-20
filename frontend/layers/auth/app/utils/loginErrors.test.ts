import { describe, expect, it } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { formatWait, loginErrorMessage, loginReasonMessage } from './loginErrors'

describe('formatWait', () => {
  it.each([
    [1, '1 segundo'],
    [45, '45 segundos'],
    [60, '1 minuto'],
    [61, '2 minutos'],
    [299, '5 minutos'],
    [3600, '1 hora'],
    [5400, '2 horas']
  ])('%i s -> %s', (seconds, text) => {
    expect(formatWait(seconds)).toBe(text)
  })
})

describe('loginErrorMessage', () => {
  it('credenciales inválidas: el mensaje del backend', () => {
    const err = new LeoApiError(401, 'invalid_credentials', 'Usuario o contraseña incorrectos.')
    expect(loginErrorMessage(err)).toBe('Usuario o contraseña incorrectos.')
  })

  it('429 con Retry-After: dice cuánto esperar', () => {
    const err = new LeoApiError(429, 'too_many_attempts', 'Demasiados intentos.', null, 120)
    expect(loginErrorMessage(err)).toBe('Demasiados intentos fallidos. Inténtalo de nuevo en 2 minutos.')
  })

  it('429 sin tiempo: mensaje genérico de espera', () => {
    const err = new LeoApiError(429, 'too_many_attempts', '')
    expect(loginErrorMessage(err)).toBe('Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.')
  })

  it('usuario inactivo: mensaje del backend', () => {
    const err = new LeoApiError(403, 'user_inactive', 'Tu usuario está desactivado.')
    expect(loginErrorMessage(err)).toBe('Tu usuario está desactivado.')
  })

  it('error de red o 500: mensaje legible, nunca crudo', () => {
    expect(loginErrorMessage(new TypeError('Failed to fetch'))).not.toMatch(/fetch/i)
    const msg = loginErrorMessage(new LeoApiError(500, 'internal_error', 'Traceback (most recent call last)'))
    expect(msg).not.toMatch(/traceback/i)
    expect(msg.length).toBeGreaterThan(10)
  })
})

describe('loginReasonMessage', () => {
  it('idle y expired explican por qué se cerró la sesión', () => {
    expect(loginReasonMessage('idle')).toBe('Tu sesión se cerró por inactividad. Inicia sesión de nuevo.')
    expect(loginReasonMessage('expired')).toBe('Tu sesión expiró. Inicia sesión de nuevo.')
  })

  it('otros valores no muestran nada', () => {
    expect(loginReasonMessage('<script>')).toBeNull()
    expect(loginReasonMessage(undefined)).toBeNull()
    expect(loginReasonMessage(['idle'])).toBeNull()
  })
})
