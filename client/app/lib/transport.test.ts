import { describe, expect, it, vi } from 'vitest'
import { base64UrlDecode, createDpopSigner, memoryDpopKeyStore } from './dpop'
import { LeoApiError } from './errors'
import { createLeoDirectTransport } from './transport'

function decode(segment: string) {
  return JSON.parse(new TextDecoder().decode(base64UrlDecode(segment)))
}

async function setup(responder: (url: string, init: RequestInit) => Response) {
  const calls: { url: string, init: RequestInit }[] = []
  const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init })
    return responder(url, init)
  })
  const onUnauthorized = vi.fn()
  const transport = createLeoDirectTransport({
    apiBase: 'http://localhost:8100/api/v1',
    publicUrl: 'http://localhost:8100',
    loginPath: '/login',
    signer: await createDpopSigner(memoryDpopKeyStore()),
    fetch: fetchMock as unknown as typeof fetch,
    onUnauthorized
  })
  return { transport, calls, onUnauthorized }
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('createLeoDirectTransport.request', () => {
  it('envía cookie (credentials: include) y una prueba DPoP con htm y htu exactos (sin query)', async () => {
    const { transport, calls } = await setup(() => json(200, { items: [] }))
    await transport.request('/users', { query: { q: 'ana', page: 2, active: true, empty: '', none: undefined } })

    const [{ url, init }] = calls as [{ url: string, init: RequestInit }]
    expect(url).toBe('http://localhost:8100/api/v1/users?q=ana&page=2&active=true')
    expect(init.credentials).toBe('include')
    const headers = new Headers(init.headers)
    const proof = headers.get('DPoP')!
    const payload = decode(proof.split('.')[1]!)
    expect(payload).toMatchObject({ htm: 'GET', htu: 'http://localhost:8100/api/v1/users' })
    expect(headers.get('Authorization')).toBeNull()
  })

  it('serializa el cuerpo JSON y usa el método indicado', async () => {
    const { transport, calls } = await setup(() => json(200, { ok: true }))
    const result = await transport.request<{ ok: boolean }>('/auth/login', { method: 'POST', body: { login: 'ana', password: 'x' } })
    expect(result).toEqual({ ok: true })
    const { init } = calls[0]!
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({ login: 'ana', password: 'x' })
    expect(decode(new Headers(init.headers).get('DPoP')!.split('.')[1]!).htm).toBe('POST')
  })

  it('cada petición lleva un jti distinto', async () => {
    const { transport, calls } = await setup(() => json(200, {}))
    await transport.request('/auth/me')
    await transport.request('/auth/me')
    const jtis = calls.map(c => decode(new Headers(c.init.headers).get('DPoP')!.split('.')[1]!).jti)
    expect(new Set(jtis).size).toBe(2)
  })

  it('204 devuelve undefined', async () => {
    const { transport } = await setup(() => new Response(null, { status: 204 }))
    await expect(transport.request('/auth/activity', { method: 'POST' })).resolves.toBeUndefined()
  })

  it('responseType blob (export CSV)', async () => {
    const { transport } = await setup(() => new Response('a,b\n1,2', { status: 200, headers: { 'Content-Type': 'text/csv' } }))
    const blob = await transport.request<Blob>('/audit/events/export', { responseType: 'blob' })
    expect(await blob.text()).toBe('a,b\n1,2')
  })

  it('error del backend → LeoApiError con code y message', async () => {
    const { transport, onUnauthorized } = await setup(() => json(403, { code: 'forbidden', message: 'No tienes permiso para realizar esta acción.' }))
    const err = await transport.request('/users').catch(e => e)
    expect(err).toBeInstanceOf(LeoApiError)
    expect(err).toMatchObject({ status: 403, code: 'forbidden' })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('401 de sesión (vencida, sin sesión o DPoP inválido) avisa a onUnauthorized', async () => {
    const { transport, onUnauthorized } = await setup(() => json(401, { code: 'session_expired', message: 'Tu sesión expiró.' }))
    await expect(transport.request('/users')).rejects.toBeInstanceOf(LeoApiError)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(onUnauthorized.mock.calls[0]![0]).toMatchObject({ code: 'session_expired' })
  })

  it('skipSessionHandling: el 401 no dispara la redirección (login, /me inicial)', async () => {
    const { transport, onUnauthorized } = await setup(() => json(401, { code: 'invalid_credentials', message: 'Usuario o contraseña incorrectos.' }))
    await expect(transport.request('/auth/login', { method: 'POST', body: {}, skipSessionHandling: true })).rejects.toMatchObject({ code: 'invalid_credentials' })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})

describe('createLeoDirectTransport: sesión', () => {
  it('me() no redirige si no hay sesión: devuelve null', async () => {
    const { transport, onUnauthorized } = await setup(() => json(401, { code: 'not_authenticated', message: 'x' }))
    await expect(transport.me()).resolves.toBeNull()
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('me() propaga otros errores (red, 5xx)', async () => {
    const { transport } = await setup(() => json(500, { code: 'internal_error', message: 'x' }))
    await expect(transport.me()).rejects.toBeInstanceOf(LeoApiError)
  })

  it('heartbeat() hace POST /auth/activity', async () => {
    const { transport, calls } = await setup(() => new Response(null, { status: 204 }))
    await transport.heartbeat()
    expect(calls[0]!.url).toBe('http://localhost:8100/api/v1/auth/activity')
    expect(calls[0]!.init.method).toBe('POST')
  })

  it('logout() hace POST /auth/logout y tolera una sesión ya vencida', async () => {
    const { transport, calls, onUnauthorized } = await setup(() => json(401, { code: 'session_expired', message: 'x' }))
    await expect(transport.logout()).resolves.toBeUndefined()
    expect(calls[0]!.url).toBe('http://localhost:8100/api/v1/auth/logout')
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('login: ruta interna con el destino de vuelta y el motivo', async () => {
    const { transport } = await setup(() => json(200, {}))
    await expect(transport.login('/users?page=2', 'idle')).resolves.toEqual({
      url: '/login?redirect=%2Fusers%3Fpage%3D2&reason=idle',
      external: false
    })
    await expect(transport.login('/')).resolves.toEqual({ url: '/login', external: false })
  })
})
