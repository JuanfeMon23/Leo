import { LeoApiError, isSessionError, leoErrorMessage } from '#leo-client/lib/errors'

/**
 * Parámetros de `/authorize` que manda la app. `dpop_jkt` es el thumbprint de la
 * llave DPoP de LA APP (no la de Leo): Leo lo reenvía tal cual para que los
 * tokens queden atados a la llave de la app.
 */
export interface AuthorizeParams {
  client_id: string
  redirect_uri: string
  state: string
  code_challenge: string
  code_challenge_method: string
  dpop_jkt: string
}

export type ParsedAuthorize =
  | { ok: true, params: AuthorizeParams }
  | { ok: false, missing: string[], message: string }

const KEYS = ['client_id', 'redirect_uri', 'state', 'code_challenge', 'code_challenge_method', 'dpop_jkt'] as const

/** Mismo patrón que `B64URL_SHA256_PATTERN` del backend (SHA-256 en base64url sin relleno). */
const B64URL_SHA256 = /^[A-Za-z0-9_-]{43}$/

export function parseAuthorizeParams(query: Record<string, unknown>): ParsedAuthorize {
  const values: Record<string, string> = {}
  const missing: string[] = []
  for (const key of KEYS) {
    const raw = query[key]
    if (typeof raw === 'string' && raw.trim()) values[key] = raw.trim()
    else missing.push(key)
  }
  if (missing.length) {
    return {
      ok: false,
      missing,
      message: `La solicitud de acceso está incompleta o es inválida (${missing.join(', ')}). Vuelve a la aplicación e inténtalo de nuevo.`
    }
  }
  if (values.code_challenge_method !== 'S256') {
    return {
      ok: false,
      missing: [],
      message: 'La solicitud de acceso no es válida: solo se admite code_challenge_method S256. Vuelve a la aplicación e inténtalo de nuevo.'
    }
  }
  if (!B64URL_SHA256.test(values.dpop_jkt!)) {
    return {
      ok: false,
      missing: [],
      message: 'La solicitud de acceso no es válida: dpop_jkt tiene un formato inválido. Vuelve a la aplicación e inténtalo de nuevo.'
    }
  }
  return { ok: true, params: values as unknown as AuthorizeParams }
}

export function buildAuthorizeRequest(params: AuthorizeParams) {
  return {
    client_id: params.client_id,
    redirect_uri: params.redirect_uri,
    state: params.state,
    code_challenge: params.code_challenge,
    code_challenge_method: params.code_challenge_method,
    dpop_jkt: params.dpop_jkt
  }
}

export type AuthorizeOutcome =
  | { status: 'redirect', url: string }
  | { status: 'login' }
  | { status: 'forbidden', message: string }
  | { status: 'error', message: string }

export interface RunAuthorizeDeps {
  params: AuthorizeParams
  request: (path: string, options: { method: 'POST', body: unknown, skipSessionHandling: boolean }) => Promise<unknown>
}

function isHttpUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false
  try {
    const { protocol } = new URL(value)
    return protocol === 'http:' || protocol === 'https:'
  } catch {
    return false
  }
}

/**
 * Pide el code a Leo (`POST /auth/authorize`) y decide qué hacer. No toca el
 * navegador: la página ejecuta el resultado (redirigir, ir al login, mostrar).
 */
export async function runAuthorize({ params, request }: RunAuthorizeDeps): Promise<AuthorizeOutcome> {
  try {
    const body = buildAuthorizeRequest(params)
    const res = await request('/auth/authorize', { method: 'POST', body, skipSessionHandling: true })
    const url = (res as { redirect_to?: unknown } | null)?.redirect_to
    if (!isHttpUrl(url)) {
      return { status: 'error', message: 'Leo devolvió una dirección de retorno inválida. Inténtalo de nuevo.' }
    }
    return { status: 'redirect', url }
  } catch (err) {
    if (isSessionError(err)) return { status: 'login' }
    if (err instanceof LeoApiError && err.status === 403 && err.code === 'access_denied') {
      return { status: 'forbidden', message: `No tienes acceso a «${params.client_id}».` }
    }
    return { status: 'error', message: leoErrorMessage(err) }
  }
}
