import { dpopHtu } from './dpop'
import type { DpopSigner } from './dpop'
import { LeoApiError, isSessionError } from './errors'
import { safeReturnTo } from './returnTo'
import type { LeoMe } from './types'

/**
 * Transporte de leo-client: cómo habla el navegador con "su" backend.
 *
 * - `leo-direct`: el frontend de Leo habla directo con la API de Leo
 *   (cookie SSO HttpOnly + header DPoP).
 * - `bff`: cada app habla con SU backend, que usa `leo_sdk` (`leo_router`:
 *   canje del code, cookies HttpOnly propias, introspección). El navegador
 *   firma DPoP con la llave de ESA app (misma lógica que `leo-direct`).
 */
export type LeoTransportKind = 'leo-direct' | 'bff'

export type LeoQueryValue = string | number | boolean | null | undefined

export interface LeoRequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  query?: Record<string, LeoQueryValue | readonly LeoQueryValue[]>
  body?: unknown
  responseType?: 'json' | 'blob'
  /** No dispara `onUnauthorized` ante un 401 (login, carga inicial de sesión). */
  skipSessionHandling?: boolean
  signal?: AbortSignal
}

export interface LeoLoginLocation {
  url: string
  /** `true`: navegación fuera de la app (p. ej. `/authorize` de Leo en `bff`). */
  external: boolean
}

export interface LeoLoginCompletion {
  me: LeoMe
  /** Ruta interna segura a la que volver (la guardada antes del login). */
  returnTo: string
}

export interface LeoTransport {
  readonly kind: LeoTransportKind
  /** Petición firmada (DPoP) con credenciales; lanza `LeoApiError`. */
  request<T = unknown>(path: string, options?: LeoRequestOptions): Promise<T>
  /** Sesión actual o `null` si no hay (401 de sesión). */
  me(): Promise<LeoMe | null>
  /** Avisa actividad al servidor (desliza la inactividad). */
  heartbeat(): Promise<void>
  /** Cierra la sesión en el servidor; tolera que ya esté vencida. */
  logout(): Promise<void>
  /** Thumbprint de la llave DPoP del dispositivo. */
  jkt(): Promise<string>
  /**
   * A dónde mandar al usuario sin sesión. Asíncrono porque en `bff` hay que
   * pedir la `authorize_url` al backend (con DPoP) antes de navegar; puede lanzar.
   */
  login(returnTo: string, reason?: string): Promise<LeoLoginLocation>
  /**
   * Solo `bff`: cierra el login al volver de Leo (`?code&state`): el backend de
   * la app fija la sesión y se devuelve el usuario y a dónde volver. Idempotente
   * para el mismo `code`+`state` (doble ejecución de la página de retorno).
   */
  completeLogin?(params: { code: string, state: string }): Promise<LeoLoginCompletion>
}

export interface LeoSignedRequesterOptions {
  apiBase: string
  publicUrl: string
  signer: DpopSigner
  fetch?: typeof fetch
  /** 401 de sesión en cualquier petición (salvo `skipSessionHandling`). */
  onUnauthorized?: (err: LeoApiError) => void
}

export interface LeoDirectTransportOptions extends LeoSignedRequesterOptions {
  loginPath: string
}

function buildUrl(apiBase: string, path: string, query?: LeoRequestOptions['query']): string {
  const joined = apiBase.replace(/\/+$/, '') + (path.startsWith('/') ? path : `/${path}`)
  // `apiBase` relativo = backend de la app en el mismo origen (proxy).
  const url = new URL(joined, globalThis.location?.origin)
  for (const [key, raw] of Object.entries(query ?? {})) {
    const values = Array.isArray(raw) ? raw : [raw]
    for (const value of values) {
      if (value === undefined || value === null || value === '') continue
      url.searchParams.append(key, String(value))
    }
  }
  return url.toString()
}

/** Petición con credenciales + prueba DPoP; común a `leo-direct` y `bff`. */
function createSignedRequester(options: LeoSignedRequesterOptions) {
  const doFetch = options.fetch ?? ((...args: Parameters<typeof fetch>) => globalThis.fetch(...args))

  return async function request<T>(path: string, opts: LeoRequestOptions = {}): Promise<T> {
    const method = opts.method ?? 'GET'
    const url = buildUrl(options.apiBase, path, opts.query)
    const headers = new Headers({ Accept: 'application/json' })
    headers.set('DPoP', await options.signer.proof(method, dpopHtu(options.publicUrl, url)))
    let body: string | undefined
    if (opts.body !== undefined) {
      headers.set('Content-Type', 'application/json')
      body = JSON.stringify(opts.body)
    }

    const response = await doFetch(url, { method, headers, body, credentials: 'include', signal: opts.signal })
    if (!response.ok) {
      const err = await LeoApiError.fromResponse(response)
      if (!opts.skipSessionHandling && isSessionError(err)) options.onUnauthorized?.(err)
      throw err
    }
    if (response.status === 204) return undefined as T
    if (opts.responseType === 'blob') return (await response.blob()) as T
    const text = await response.text()
    return (text ? JSON.parse(text) : undefined) as T
  }
}

export function createLeoDirectTransport(options: LeoDirectTransportOptions): LeoTransport {
  const request = createSignedRequester(options)

  return {
    kind: 'leo-direct',
    request,
    async me() {
      try {
        return await request<LeoMe>('/auth/me', { skipSessionHandling: true })
      } catch (err) {
        if (isSessionError(err)) return null
        throw err
      }
    },
    async heartbeat() {
      await request('/auth/activity', { method: 'POST' })
    },
    async logout() {
      try {
        await request('/auth/logout', { method: 'POST', skipSessionHandling: true })
      } catch (err) {
        if (!isSessionError(err)) throw err
      }
    },
    jkt: () => options.signer.jkt(),
    async login(returnTo, reason) {
      const params = new URLSearchParams()
      if (returnTo && returnTo !== '/') params.set('redirect', returnTo)
      if (reason) params.set('reason', reason)
      const qs = params.toString()
      return { url: qs ? `${options.loginPath}?${qs}` : options.loginPath, external: false }
    }
  }
}

// ── bff ────────────────────────────────────────────────────────────────

/** Dónde se recuerda a dónde volver mientras el navegador visita a Leo. */
export interface LeoReturnStore {
  get(): string | null
  set(value: string): void
  clear(): void
}

const RETURN_KEY = 'leo:return-to'

/** `sessionStorage` (solo una ruta interna, nada sensible); memoria si no hay. */
export function sessionReturnStore(): LeoReturnStore {
  let memory: string | null = null
  const storage = (): Storage | null => {
    try {
      return globalThis.sessionStorage ?? null
    } catch {
      return null
    }
  }
  return {
    get() {
      try {
        return storage()?.getItem(RETURN_KEY) ?? memory
      } catch {
        return memory
      }
    },
    set(value) {
      memory = value
      try {
        storage()?.setItem(RETURN_KEY, value)
      } catch { /* sin almacenamiento: queda en memoria */ }
    },
    clear() {
      memory = null
      try {
        storage()?.removeItem(RETURN_KEY)
      } catch { /* idem */ }
    }
  }
}

export interface LeoBffTransportOptions extends LeoSignedRequesterOptions {
  /** Prefijo de `leo_router` en el backend de la app. Por defecto `/auth`. */
  authPath?: string
  /**
   * `leo_sdk` no devuelve el tiempo de inactividad en `/auth/me`: se usa este
   * valor (segundos; política de Leo: 1800) salvo que el backend lo envíe.
   */
  idleTimeoutSeconds?: number
  returnStore?: LeoReturnStore
}

/** Cuerpo de `/auth/me` y `/auth/callback` de `leo_sdk` (`LeoUser.public()`). */
export interface LeoSdkMeBody {
  user: {
    id: string
    username: string
    name?: string
    first_name?: string
    last_name?: string
    email?: string
    permissions?: string[]
    session_id?: string
  }
  /** Opcionales: `leo_sdk` aún no los entrega; si llegan, se respetan. */
  session?: Partial<LeoMe['session']>
  applications?: LeoMe['applications']
}

/** Adapta la forma del SDK a `LeoMe`; lo que el SDK no da queda con valor por defecto. */
export function toLeoMe(body: LeoSdkMeBody, defaultIdleTimeoutSeconds: number): LeoMe {
  const user = body.user
  return {
    user: {
      id: user.id,
      username: user.username,
      name: user.name ?? '',
      email: user.email ?? '',
      // El SDK entrega `name` y, desde `LeoUser.public()`, first_name/last_name.
      first_name: user.first_name ?? user.name ?? '',
      last_name: user.last_name ?? ''
    },
    session: {
      id: body.session?.id ?? user.session_id ?? '',
      expires_at: body.session?.expires_at ?? '',
      last_activity_at: body.session?.last_activity_at ?? '',
      idle_timeout_seconds: body.session?.idle_timeout_seconds ?? defaultIdleTimeoutSeconds
    },
    permissions: [...(user.permissions ?? [])],
    applications: body.applications ?? []
  }
}

function parseAuthorizeUrl(value: unknown): URL | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url : null
  } catch {
    return null
  }
}

export function createLeoBffTransport(options: LeoBffTransportOptions): LeoTransport {
  const request = createSignedRequester(options)
  const authPath = (options.authPath ?? '/auth').replace(/\/+$/, '')
  const idleTimeout = options.idleTimeoutSeconds ?? 1800
  const returnStore = options.returnStore ?? sessionReturnStore()
  const completions = new Map<string, Promise<LeoLoginCompletion>>()

  return {
    kind: 'bff',
    request,
    async me() {
      try {
        return toLeoMe(await request<LeoSdkMeBody>(`${authPath}/me`, { skipSessionHandling: true }), idleTimeout)
      } catch (err) {
        if (isSessionError(err)) return null
        throw err
      }
    },
    async heartbeat() {
      await request(`${authPath}/activity`, { method: 'POST' })
    },
    async logout() {
      try {
        await request(`${authPath}/logout`, { method: 'POST', skipSessionHandling: true })
      } catch (err) {
        if (!isSessionError(err)) throw err
      }
    },
    jkt: () => options.signer.jkt(),
    async login(returnTo) {
      // Antes de salir de la SPA: la navegación a Leo no lleva estado.
      returnStore.set(safeReturnTo(returnTo))
      const body = await request<{ authorize_url?: unknown }>(`${authPath}/login`, { skipSessionHandling: true })
      const url = parseAuthorizeUrl(body?.authorize_url)
      // La llave de la app es la que presentará los tokens: el flujo debe ir atado a ella.
      if (!url || url.searchParams.get('dpop_jkt') !== await options.signer.jkt()) {
        throw new LeoApiError(400, 'invalid_authorize_url', 'No se pudo iniciar el inicio de sesión. Intenta de nuevo.')
      }
      return { url: url.toString(), external: true }
    },
    completeLogin({ code, state }) {
      const key = `${code}\n${state}`
      let pending = completions.get(key)
      if (!pending) {
        pending = (async () => {
          const body = await request<LeoSdkMeBody>(`${authPath}/callback`, { query: { code, state }, skipSessionHandling: true })
          const returnTo = safeReturnTo(returnStore.get())
          returnStore.clear()
          return { me: toLeoMe(body, idleTimeout), returnTo }
        })()
        completions.set(key, pending)
      }
      return pending
    }
  }
}
