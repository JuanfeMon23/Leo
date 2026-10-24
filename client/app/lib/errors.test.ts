import { describe, expect, it } from 'vitest'
import { LeoApiError, isForbiddenError, isSessionError, leoErrorMessage } from './errors'

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })
}

describe('LeoApiError.fromResponse', () => {
  it('toma code, message y details del formato único del backend', async () => {
    const err = await LeoApiError.fromResponse(
      jsonResponse(409, { code: 'duplicate', message: 'Ya existe un usuario con usuario «ana».', details: { username: 'ana' } })
    )
    expect(err).toBeInstanceOf(LeoApiError)
    expect(err).toMatchObject({ status: 409, code: 'duplicate', details: { username: 'ana' } })
    expect(err.message).toBe('Ya existe un usuario con usuario «ana».')
  })

  it('429: segundos de espera desde details o desde Retry-After', async () => {
    const fromDetails = await LeoApiError.fromResponse(
      jsonResponse(429, { code: 'too_many_attempts', message: 'Demasiados intentos.', details: { retry_after_seconds: 42 } })
    )
    expect(fromDetails.retryAfterSeconds).toBe(42)
    const fromHeader = await LeoApiError.fromResponse(
      jsonResponse(429, { code: 'too_many_attempts', message: 'Demasiados intentos.' }, { 'Retry-After': '30' })
    )
    expect(fromHeader.retryAfterSeconds).toBe(30)
  })

  it('cuerpo que no es JSON (proxy, HTML): error genérico sin texto crudo', async () => {
    const err = await LeoApiError.fromResponse(new Response('<html>502 Bad Gateway</html>', { status: 502 }))
    expect(err.status).toBe(502)
    expect(err.code).toBe('http_error')
    expect(leoErrorMessage(err)).not.toMatch(/html|502/i)
  })

  it('422 con detalles por campo queda listo para mapApiErrorToForm (forma FastAPI)', async () => {
    const err = await LeoApiError.fromResponse(
      jsonResponse(422, {
        code: 'validation_error',
        message: 'Hay datos inválidos en la solicitud: email: No tiene el formato esperado.',
        details: [{ field: 'email', message: 'No tiene el formato esperado.' }]
      })
    )
    expect(err.data).toEqual({ detail: [{ loc: ['email'], msg: 'No tiene el formato esperado.' }] })
  })
})

describe('leoErrorMessage', () => {
  it('muestra el mensaje en español del backend aunque sea 401/403', () => {
    expect(leoErrorMessage(new LeoApiError(401, 'invalid_credentials', 'Usuario o contraseña incorrectos.'))).toBe(
      'Usuario o contraseña incorrectos.'
    )
    expect(
      leoErrorMessage(new LeoApiError(403, 'access_denied', 'No tienes acceso a «Vladimir». Pide a un administrador que te asigne un rol en esa aplicación.'))
    ).toContain('No tienes acceso a «Vladimir»')
  })

  it('5xx: mensaje genérico, nunca el texto del servidor', () => {
    const msg = leoErrorMessage(new LeoApiError(500, 'internal_error', 'Traceback (most recent call last) ...'))
    expect(msg).not.toMatch(/traceback/i)
    expect(msg).toMatch(/servidor/i)
  })

  it('mensaje técnico del backend: se reemplaza por uno legible', () => {
    expect(leoErrorMessage(new LeoApiError(409, 'duplicate', 'IntegrityError: duplicate key violates unique constraint'))).not.toMatch(/integrity/i)
  })

  it('error de red (fetch sin respuesta): mensaje de conexión', () => {
    expect(leoErrorMessage(new TypeError('Failed to fetch'))).toMatch(/conectar/i)
  })
})

describe('isSessionError', () => {
  it('reconoce los 401 de sesión', () => {
    for (const code of ['not_authenticated', 'session_expired', 'invalid_dpop_proof']) {
      expect(isSessionError(new LeoApiError(401, code, 'x'))).toBe(true)
    }
  })

  it('no confunde credenciales inválidas ni 403 con sesión vencida', () => {
    expect(isSessionError(new LeoApiError(401, 'invalid_credentials', 'x'))).toBe(false)
    expect(isSessionError(new LeoApiError(403, 'forbidden', 'x'))).toBe(false)
    expect(isSessionError(new Error('x'))).toBe(false)
  })
})

describe('leoErrorMessage: 422 de page_size', () => {
  const err = (details: unknown, message = 'Hay datos inválidos en la solicitud.') =>
    new LeoApiError(422, 'validation_error', message, details)

  it('forma Incubus (details objeto): usa el message legible del backend', () => {
    expect(leoErrorMessage(err({ field: 'page_size', max: 50 }, 'El tamaño de página máximo permitido es 50.')))
      .toBe('El tamaño de página máximo permitido es 50.')
  })

  it('forma Leo/Vladimir (details lista): máximo desde max', () => {
    expect(leoErrorMessage(err([{ field: 'page_size', message: 'x', max: 100 }])))
      .toBe('Se pidieron demasiados registros por página: el máximo permitido es 100.')
  })

  it('forma lista: máximo desde el final del texto', () => {
    expect(leoErrorMessage(err([{ field: 'page_size', message: 'Input should be less than or equal to 50' }])))
      .toContain('es 50.')
  })

  it('sin máximo conocido no inventa cifra', () => {
    expect(leoErrorMessage(err([{ field: 'page_size', message: 'raro' }])))
      .toBe('Se pidieron demasiados registros por página.')
  })

  it('otros 422 siguen mostrando el message del backend', () => {
    expect(leoErrorMessage(err([{ field: 'name', message: 'x' }], 'Algunos datos no son válidos.')))
      .toBe('Algunos datos no son válidos.')
  })
})

describe('401 de sesión sin ruido', () => {
  it('leoErrorMessage da un mensaje neutro (ya se redirige) y isForbiddenError distingue forbidden', () => {
    expect(leoErrorMessage(new LeoApiError(401, 'session_expired', 'Tu sesión expiró.'))).toBe('Redirigiendo al inicio de sesión…')
    expect(isForbiddenError(new LeoApiError(403, 'forbidden', 'x'))).toBe(true)
    expect(isForbiddenError(new LeoApiError(403, 'account_locked', 'x'))).toBe(false)
  })
})
