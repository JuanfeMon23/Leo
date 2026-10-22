import { describe, expect, it, vi } from 'vitest'
import { base64UrlDecode, createDpopSigner, jwkThumbprint, memoryDpopKeyStore } from './dpop'
import { LeoApiError, leoErrorMessage } from './errors'
import { createLeoBffTransport, toLeoMe } from './transport'
import type { LeoReturnStore } from './transport'

const BACKEND = 'http://localhost:8200'
const LEO = 'http://localhost:3100'
const SDK_USER = {
  id: '6f1c2a52-0000-4000-8000-000000000001',
  username: 'ana',
  name: 'Ana Pérez',
  email: 'ana@example.com',
  permissions: ['vladimir.samples.edit', 'vladimir.samples.view'],
  session_id: '6f1c2a52-0000-4000-8000-000000000002'
}

function decodeJwt(proof: string) {
  const [h, p] = proof.split('.') as [string, string]
  const parse = (s: string) => JSON.parse(new TextDecoder().decode(base64UrlDecode(s)))
  return { header: parse(h), payload: parse(p) }
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const apiError = (status: number, code: string, message = 'Mensaje en español.') => json(status, { code, message, details: null })

function memoryReturnStore(): LeoReturnStore {
  let value: string | null = null
  return { get: () => value, set: (v) => { value = v }, clear: () => { value = null } }
}

/**
 * Backend de la app con `leo_router` simulado fielmente: exige DPoP con `htu`
 * = PUBLIC_URL + path, liga el flujo al `jkt` de la prueba y devuelve las
 * formas de `LeoUser.public()`.
 */
function fakeBackend() {
  const calls: { url: string, method: string, headers: Headers, credentials?: RequestCredentials }[] = []
  let flow: { state: string, jkt: string } | null = null
  let authenticated = false
  const state = { codeUses: 0 }

  const handler = async (input: string, init: RequestInit = {}): Promise<Response> => {
    const url = new URL(input)
    const method = init.method ?? 'GET'
    const headers = new Headers(init.headers)
    calls.push({ url: input, method, headers, credentials: init.credentials })

    const proof = headers.get('DPoP')
    if (!proof) return apiError(401, 'invalid_dpop_proof')
    const { header, payload } = decodeJwt(proof)
    if (payload.htu !== BACKEND + url.pathname || payload.htm !== method) return apiError(401, 'invalid_dpop_proof')
    const jkt = await jwkThumbprint(header.jwk)

    switch (`${method} ${url.pathname}`) {
      case 'GET /auth/login':
        flow = { state: 'state-123', jkt }
        return json(200, {
          authorize_url: `${LEO}/authorize?${new URLSearchParams({
            client_id: 'vladimir',
            redirect_uri: `${BACKEND}/auth/callback`,
            state: flow.state,
            code_challenge: 'x'.repeat(43),
            code_challenge_method: 'S256',
            dpop_jkt: jkt
          })}`
        })
      case 'GET /auth/callback': {
        const code = url.searchParams.get('code')
        if (!flow || url.searchParams.get('state') !== flow.state || flow.jkt !== jkt) {
          return apiError(400, 'invalid_state', 'La solicitud de inicio de sesión expiró o no es válida.')
        }
        if (code !== 'good-code' || state.codeUses++ > 0) return apiError(400, 'invalid_grant')
        authenticated = true
        return json(200, { user: SDK_USER })
      }
      case 'GET /auth/me':
        return authenticated ? json(200, { user: SDK_USER }) : apiError(401, 'not_authenticated')
      case 'POST /auth/activity':
        return authenticated ? new Response(null, { status: 204 }) : apiError(401, 'session_expired')
      case 'POST /auth/logout':
        authenticated = false
        return new Response(null, { status: 204 })
      default:
        return apiError(404, 'not_found')
    }
  }
  return { calls, handler, setAuthenticated: (v: boolean) => { authenticated = v } }
}

async function setup(overrides: { handler?: (url: string, init?: RequestInit) => Promise<Response> | Response } = {}) {
  const backend = fakeBackend()
  const fetchMock = vi.fn(overrides.handler ?? backend.handler)
  const onUnauthorized = vi.fn()
  const signer = await createDpopSigner(memoryDpopKeyStore())
  const returnStore = memoryReturnStore()
  const transport = createLeoBffTransport({
    apiBase: BACKEND,
    publicUrl: BACKEND,
    signer,
    returnStore,
    fetch: fetchMock as unknown as typeof fetch,
    onUnauthorized
  })
  return { transport, backend, fetchMock, onUnauthorized, returnStore, signer }
}

describe('createLeoBffTransport: login', () => {
  it('pide /auth/login con DPoP y devuelve la authorize_url como navegación externa', async () => {
    const { transport, backend } = await setup()
    const location = await transport.login('/muestras?page=2')

    expect(location.external).toBe(true)
    expect(location.url.startsWith(`${LEO}/authorize?`)).toBe(true)
    const [call] = backend.calls
    expect(call).toMatchObject({ url: `${BACKEND}/auth/login`, method: 'GET', credentials: 'include' })
    const { header, payload } = decodeJwt(call!.headers.get('DPoP')!)
    expect(header).toMatchObject({ typ: 'dpop+jwt', alg: 'ES256' })
    expect(payload).toMatchObject({ htm: 'GET', htu: `${BACKEND}/auth/login` })
  })

  it('el dpop_jkt de authorize_url es el de la llave de la app', async () => {
    const { transport, signer } = await setup()
    const { url } = await transport.login('/')
    expect(new URL(url).searchParams.get('dpop_jkt')).toBe(await signer.jkt())
    expect(await transport.jkt()).toBe(await signer.jkt())
  })

  it('rechaza una authorize_url atada a otra llave o no http(s)', async () => {
    for (const authorize_url of [`${LEO}/authorize?dpop_jkt=otra-llave`, 'javascript:alert(1)', 42]) {
      const { transport } = await setup({ handler: () => json(200, { authorize_url }) })
      const err = await transport.login('/').catch(e => e)
      expect(err).toBeInstanceOf(LeoApiError)
      expect(leoErrorMessage(err)).toMatch(/inicio de sesión/)
    }
  })

  it('un error del backend al pedir el login no dispara onUnauthorized (sin bucle)', async () => {
    const { transport, onUnauthorized } = await setup({ handler: () => apiError(401, 'invalid_dpop_proof', 'Recarga la página.') })
    await expect(transport.login('/')).rejects.toMatchObject({ code: 'invalid_dpop_proof' })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})

describe('createLeoBffTransport: retorno (callback)', () => {
  it('login → callback fija el usuario y vuelve a la ruta de origen', async () => {
    const { transport, backend, returnStore } = await setup()
    await transport.login('/muestras?page=2')
    expect(returnStore.get()).toBe('/muestras?page=2')

    const { me, returnTo } = await transport.completeLogin!({ code: 'good-code', state: 'state-123' })
    expect(returnTo).toBe('/muestras?page=2')
    expect(returnStore.get()).toBeNull()
    expect(me.user).toMatchObject({ id: SDK_USER.id, username: 'ana', email: 'ana@example.com', first_name: 'Ana Pérez' })
    expect(me.permissions).toEqual(['vladimir.samples.edit', 'vladimir.samples.view'])

    const callback = backend.calls.at(-1)!
    expect(callback.url).toBe(`${BACKEND}/auth/callback?code=good-code&state=state-123`)
    // htu sin query
    expect(decodeJwt(callback.headers.get('DPoP')!).payload.htu).toBe(`${BACKEND}/auth/callback`)
  })

  it('es tolerante a la doble ejecución: un solo canje por code+state', async () => {
    const { transport, backend } = await setup()
    await transport.login('/a')
    const params = { code: 'good-code', state: 'state-123' }
    const [first, second] = await Promise.all([transport.completeLogin!(params), transport.completeLogin!(params)])
    expect(second).toBe(first)
    expect(await transport.completeLogin!(params)).toBe(first)
    expect(backend.calls.filter(c => c.url.includes('/auth/callback'))).toHaveLength(1)
  })

  it('sin ruta guardada o con una insegura vuelve a /', async () => {
    const a = await setup()
    await a.transport.login('/')
    a.returnStore.set('//evil.example')
    expect((await a.transport.completeLogin!({ code: 'good-code', state: 'state-123' })).returnTo).toBe('/')
  })

  it('state inválido → invalid_state con mensaje legible', async () => {
    const { transport, onUnauthorized } = await setup()
    await transport.login('/')
    const err = await transport.completeLogin!({ code: 'good-code', state: 'otro' }).catch(e => e)
    expect(err).toMatchObject({ status: 400, code: 'invalid_state' })
    expect(leoErrorMessage(err)).toBe('La solicitud de inicio de sesión expiró o no es válida.')
    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})

describe('createLeoBffTransport: sesión', () => {
  it('me() sin sesión devuelve null; con sesión adapta la forma del SDK', async () => {
    const { transport, backend, onUnauthorized } = await setup()
    await expect(transport.me()).resolves.toBeNull()
    backend.setAuthenticated(true)
    const me = await transport.me()
    expect(me).toMatchObject({
      user: { username: 'ana', first_name: 'Ana Pérez', last_name: '' },
      permissions: SDK_USER.permissions,
      applications: [],
      // valor por defecto documentado: el SDK no entrega el tiempo de inactividad
      session: { id: SDK_USER.session_id, idle_timeout_seconds: 1800 }
    })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('invalid_dpop_proof en me() también es "sin sesión"', async () => {
    const { transport } = await setup({ handler: () => apiError(401, 'invalid_dpop_proof') })
    await expect(transport.me()).resolves.toBeNull()
  })

  it('me() propaga errores de red/5xx', async () => {
    const { transport } = await setup({ handler: () => apiError(500, 'internal_error') })
    await expect(transport.me()).rejects.toBeInstanceOf(LeoApiError)
  })

  it('heartbeat() hace POST /auth/activity (204) con DPoP', async () => {
    const { transport, backend } = await setup()
    backend.setAuthenticated(true)
    await expect(transport.heartbeat()).resolves.toBeUndefined()
    const call = backend.calls.at(-1)!
    expect(call).toMatchObject({ url: `${BACKEND}/auth/activity`, method: 'POST' })
    expect(call.headers.get('DPoP')).toBeTruthy()
  })

  it('heartbeat() con sesión vencida avisa a onUnauthorized', async () => {
    const { transport, onUnauthorized } = await setup()
    await expect(transport.heartbeat()).rejects.toMatchObject({ code: 'session_expired' })
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('logout() hace POST /auth/logout y tolera sesión vencida', async () => {
    const { transport, backend } = await setup()
    backend.setAuthenticated(true)
    await transport.logout()
    expect(backend.calls.at(-1)).toMatchObject({ url: `${BACKEND}/auth/logout`, method: 'POST' })
    const expired = await setup({ handler: () => apiError(401, 'session_expired') })
    await expect(expired.transport.logout()).resolves.toBeUndefined()
    expect(expired.onUnauthorized).not.toHaveBeenCalled()
  })

  it('logout() propaga errores que no son de sesión', async () => {
    const { transport } = await setup({ handler: () => apiError(500, 'internal_error') })
    await expect(transport.logout()).rejects.toBeInstanceOf(LeoApiError)
  })
})

describe('createLeoBffTransport: request y configuración', () => {
  it('request a la API de la app: cookie + DPoP con htu = URL pública + path; 403 legible', async () => {
    const { transport, fetchMock } = await setup({
      handler: () => apiError(403, 'forbidden', 'No tienes permiso para realizar esta acción.')
    })
    const err = await transport.request('/things', { query: { q: 'x' } }).catch(e => e)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe(`${BACKEND}/things?q=x`)
    expect(init.credentials).toBe('include')
    expect(decodeJwt(new Headers(init.headers).get('DPoP')!).payload).toMatchObject({ htm: 'GET', htu: `${BACKEND}/things` })
    expect(leoErrorMessage(err)).toBe('No tienes permiso para realizar esta acción.')
  })

  it('401 de sesión en una petición de la app avisa a onUnauthorized', async () => {
    const { transport, onUnauthorized } = await setup({ handler: () => apiError(401, 'not_authenticated') })
    await expect(transport.request('/things')).rejects.toBeInstanceOf(LeoApiError)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('el prefijo de auth es configurable', async () => {
    const backend = fakeBackend()
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => backend.handler(url.replace('/leo-auth', '/auth'), init))
    const transport = createLeoBffTransport({
      apiBase: BACKEND,
      publicUrl: BACKEND,
      signer: await createDpopSigner(memoryDpopKeyStore()),
      authPath: '/leo-auth/',
      fetch: fetchMock as unknown as typeof fetch
    })
    // El htu de la prueba lleva /leo-auth: el backend simulado (que espera /auth) lo rechaza,
    // lo que demuestra que el path solicitado es el configurado.
    expect(fetchMock).not.toHaveBeenCalled()
    await transport.me().catch(() => {})
    expect(fetchMock.mock.calls[0]![0]).toBe(`${BACKEND}/leo-auth/me`)
  })

  it('idleTimeoutSeconds configurable y el SDK futuro (session/applications) se respeta', () => {
    const body = {
      user: SDK_USER,
      session: { idle_timeout_seconds: 600 },
      applications: [{ slug: 'vladimir', name: 'Vladimir', base_url: 'http://localhost:3200' }]
    }
    expect(toLeoMe(body, 1800).session.idle_timeout_seconds).toBe(600)
    expect(toLeoMe(body, 1800).applications).toHaveLength(1)
    expect(toLeoMe({ user: SDK_USER }, 900).session.idle_timeout_seconds).toBe(900)
  })
})

describe('toLeoMe nombres', () => {
  it('usa first_name/last_name del SDK y cae a name cuando no llegan', () => {
    const base = { id: 'u', username: 'ana', name: 'Ana Pérez' }
    expect(toLeoMe({ user: { ...base, first_name: 'Ana', last_name: 'Pérez' } }, 1).user)
      .toMatchObject({ name: 'Ana Pérez', first_name: 'Ana', last_name: 'Pérez' })
    expect(toLeoMe({ user: base }, 1).user).toMatchObject({ name: 'Ana Pérez', first_name: 'Ana Pérez', last_name: '' })
  })
})
