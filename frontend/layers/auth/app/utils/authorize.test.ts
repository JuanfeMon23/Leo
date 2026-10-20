import { describe, expect, it, vi } from 'vitest'
import { LeoApiError } from '#leo-client/lib/errors'
import { buildAuthorizeRequest, parseAuthorizeParams, runAuthorize } from './authorize'

const CHALLENGE = 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM'
const APP_JKT = 'NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs'
const valid = {
  client_id: 'vladimir',
  redirect_uri: 'http://localhost:3200/auth/callback',
  state: 'abc123',
  code_challenge: CHALLENGE,
  code_challenge_method: 'S256',
  dpop_jkt: APP_JKT
}

describe('parseAuthorizeParams', () => {
  it('acepta los 6 parámetros', () => {
    expect(parseAuthorizeParams(valid)).toEqual({ ok: true, params: valid })
  })

  it.each(Object.keys(valid))('falta %s: error que lo nombra', (key) => {
    const query: Record<string, unknown> = { ...valid }
    delete query[key]
    const result = parseAuthorizeParams(query)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.missing).toEqual([key])
      expect(result.message).toContain(key)
    }
  })

  it('vacío o solo espacios cuenta como faltante', () => {
    expect(parseAuthorizeParams({ ...valid, state: '  ' }).ok).toBe(false)
  })

  it('solo admite S256', () => {
    const result = parseAuthorizeParams({ ...valid, code_challenge_method: 'plain' })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.message).toMatch(/S256/)
  })

  it('dpop_jkt mal formado (no base64url de 43 caracteres): enlace inválido', () => {
    for (const bad of ['JKT', `${APP_JKT}=`, `${APP_JKT}A`, 'a'.repeat(42), `${'a'.repeat(42)}+`, `${'a'.repeat(42)}.`]) {
      const result = parseAuthorizeParams({ ...valid, dpop_jkt: bad })
      expect(result.ok).toBe(false)
      if (!result.ok) {
        expect(result.message).toContain('dpop_jkt')
        expect(result.message).toMatch(/inválid/)
      }
    }
  })

  it('un parámetro repetido (arreglo) no es válido', () => {
    expect(parseAuthorizeParams({ ...valid, client_id: ['a', 'b'] }).ok).toBe(false)
  })
})

describe('buildAuthorizeRequest', () => {
  it('arma el cuerpo de POST /auth/authorize con el dpop_jkt de la app', () => {
    expect(buildAuthorizeRequest(valid)).toEqual({
      client_id: 'vladimir',
      redirect_uri: valid.redirect_uri,
      state: 'abc123',
      code_challenge: CHALLENGE,
      code_challenge_method: 'S256',
      dpop_jkt: APP_JKT
    })
  })
})

describe('runAuthorize', () => {
  const fail = (err: unknown) => vi.fn(async () => { throw err })

  it('éxito: pide el code y devuelve la URL de redirección', async () => {
    const request = vi.fn(async () => ({ redirect_to: 'http://localhost:3200/auth/callback?code=c&state=abc123' }))
    const out = await runAuthorize({ params: valid, request })
    expect(out).toEqual({ status: 'redirect', url: 'http://localhost:3200/auth/callback?code=c&state=abc123' })
    expect(request).toHaveBeenCalledWith('/auth/authorize', {
      method: 'POST',
      body: buildAuthorizeRequest(valid),
      skipSessionHandling: true
    })
  })

  it('envía exactamente el dpop_jkt de la URL de la app (nunca la llave de Leo)', async () => {
    const request = vi.fn(async (_path: string, _options: { method: 'POST', body: unknown, skipSessionHandling: boolean }) => ({ redirect_to: 'http://localhost:3200/cb?code=c' }))
    await runAuthorize({ params: valid, request })
    expect((request.mock.calls[0]![1].body as { dpop_jkt: string }).dpop_jkt).toBe(APP_JKT)
  })

  it('rechaza una redirección que no sea http(s)', async () => {
    const request = vi.fn(async () => ({ redirect_to: 'javascript:alert(1)' }))
    expect((await runAuthorize({ params: valid, request })).status).toBe('error')
  })

  it('401 de sesión: pide ir al login', async () => {
    const request = fail(new LeoApiError(401, 'not_authenticated', 'No has iniciado sesión.'))
    expect(await runAuthorize({ params: valid, request })).toEqual({ status: 'login' })
  })

  it('403 access_denied: sin acceso a la app', async () => {
    const request = fail(new LeoApiError(403, 'access_denied', 'x'))
    expect(await runAuthorize({ params: valid, request })).toEqual({
      status: 'forbidden',
      message: 'No tienes acceso a «vladimir».'
    })
  })

  it('otros 403 (usuario inactivo): mensaje legible del backend', async () => {
    const request = fail(new LeoApiError(403, 'user_inactive', 'Tu usuario está desactivado.'))
    expect(await runAuthorize({ params: valid, request })).toEqual({
      status: 'error',
      message: 'Tu usuario está desactivado.'
    })
  })

  it('400 invalid_redirect_uri: error legible', async () => {
    const request = fail(new LeoApiError(400, 'invalid_redirect_uri', 'La dirección de retorno no está registrada.'))
    expect(await runAuthorize({ params: valid, request })).toEqual({
      status: 'error',
      message: 'La dirección de retorno no está registrada.'
    })
  })

  it('error de red: mensaje legible, no el crudo', async () => {
    const out = await runAuthorize({ params: valid, request: fail(new TypeError('Failed to fetch')) })
    expect(out.status).toBe('error')
    if (out.status === 'error') expect(out.message).not.toMatch(/fetch/i)
  })
})
