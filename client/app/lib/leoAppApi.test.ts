import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LeoApiError } from './errors'
import { createLeoAppApi } from './leoAppApi'
import { toLeoPath } from './leoPaths'
import { forbiddenMessage, registerPermissionNames } from './permissionNames'
import { cacheKey } from './requestCache'

describe('toLeoPath', () => {
  it('deriva el prefijo de la diferencia entre ambas bases', () => {
    expect(toLeoPath('http://h:8200/api/v1/', 'http://h:8200', 'staff')).toBe('/api/v1/staff')
    expect(toLeoPath('http://h:8200/api/v1', 'http://h:8200/', '/staff')).toBe('/api/v1/staff')
  })
  it('falla si la API no cuelga de la base de Leo', () => {
    expect(() => toLeoPath('http://a/api', 'http://b', '/x')).toThrow()
  })
})

describe('forbiddenMessage', () => {
  beforeEach(() => registerPermissionNames({ 'app.a.view': 'Consultar A', 'app.a.edit': 'Editar A' }))

  it('nombra action, any_of (sin repetir) y usa el respaldo si se desconoce', () => {
    expect(forbiddenMessage({ action: 'app.a.view' }, 'x')).toBe('No tienes permiso para: Consultar A')
    expect(forbiddenMessage({ any_of: ['app.a.view', 'app.a.edit', 'app.a.view'] }, 'x')).toBe('No tienes permiso para: Consultar A o Editar A')
    expect(forbiddenMessage({ action: 'otro.tag' }, 'respaldo')).toBe('respaldo')
    expect(forbiddenMessage(null, 'respaldo')).toBe('respaldo')
  })
})

describe('createLeoAppApi', () => {
  const send = vi.fn()
  const api = createLeoAppApi(send as never, path => `/api/v1${path}`)
  beforeEach(() => {
    send.mockReset()
    send.mockResolvedValue({ ok: true })
  })

  it('cada verbo fija método, cuerpo y query (params es alias)', async () => {
    await api.post('/s', { a: 1 })
    await api.get('/s', { params: { page: 2 } })
    expect(send).toHaveBeenNthCalledWith(1, '/api/v1/s', expect.objectContaining({ method: 'POST', body: { a: 1 } }))
    expect(send).toHaveBeenNthCalledWith(2, '/api/v1/s', expect.objectContaining({ method: 'GET', query: { page: 2 } }))
  })

  it('cacheTtl reutiliza el GET y una mutación lo invalida', async () => {
    await api.get('/cat', { cacheTtl: 60_000 })
    await api.get('/cat', { cacheTtl: 60_000 })
    expect(send).toHaveBeenCalledTimes(1)
    await api.patch('/cat/1', {})
    await api.get('/cat', { cacheTtl: 60_000 })
    expect(send).toHaveBeenCalledTimes(3)
  })

  it('un 403 forbidden nombra el permiso faltante', async () => {
    registerPermissionNames({ 'app.b.view': 'Consultar B' })
    send.mockRejectedValue(new LeoApiError(403, 'forbidden', 'Prohibido', { action: 'app.b.view' }))
    await expect(api.get('/b')).rejects.toMatchObject({ status: 403, message: 'No tienes permiso para: Consultar B' })
  })

  it('un error que no es 403 se propaga igual', async () => {
    const err = new LeoApiError(500, 'internal', 'x')
    send.mockRejectedValue(err)
    await expect(api.delete('/b/1')).rejects.toBe(err)
  })
})

describe('cacheKey', () => {
  it('ignora vacíos y el orden', () => {
    expect(cacheKey('/s', { b: 1, a: 2, c: '', d: undefined })).toBe(cacheKey('/s', { a: 2, b: 1 }))
  })
})

describe('422 de FastAPI', () => {
  it('se mapea a validation_error con campos (sin prefijo body)', async () => {
    const res = new Response(JSON.stringify({ detail: [{ loc: ['body', 'name'], msg: 'Campo requerido', type: 'missing' }] }), { status: 422 })
    const err = await LeoApiError.fromResponse(res)
    expect(err).toMatchObject({ status: 422, code: 'validation_error' })
    expect(err.data).toEqual({ detail: [{ loc: ['name'], msg: 'Campo requerido' }] })
  })
})
