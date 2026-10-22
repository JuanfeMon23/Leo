import { LeoApiError } from './errors'
import { forbiddenMessage } from './permissionNames'
import type { ForbiddenDetails } from './permissionNames'
import { cacheKey, cachedRequest, invalidateCaches } from './requestCache'
import type { LeoRequestOptions } from './transport'

type Query = NonNullable<LeoRequestOptions['query']>

/** Opciones de una llamada; `cacheTtl` (ms) solo aplica a GET JSON. */
export interface LeoAppRequestOptions {
  query?: Query
  /** Alias de `query`. */
  params?: Query
  signal?: AbortSignal
  responseType?: 'json' | 'blob'
  /** Guarda la respuesta del GET en la caché del navegador por ese tiempo (ms). */
  cacheTtl?: number
}

export type LeoSend = <T>(path: string, options?: LeoRequestOptions) => Promise<T>

/** Un 403 `forbidden` nombra el permiso que falta ("No tienes permiso para: …"). */
function withPermissionName(err: unknown): unknown {
  if (err instanceof LeoApiError && err.status === 403 && err.code === 'forbidden') {
    const message = forbiddenMessage(err.details as ForbiddenDetails | null, err.message)
    return new LeoApiError(err.status, err.code, message, err.details, err.retryAfterSeconds)
  }
  return err
}

/**
 * Cliente de verbos sobre el solicitante firmado de leo-client. Lanza
 * `LeoApiError` (422 de FastAPI ya mapeado a `validation_error`). Toda
 * mutación exitosa invalida TODO lo cacheado (listados y catálogos).
 */
export function createLeoAppApi(send: LeoSend, toPath: (path: string) => string) {
  async function request<T>(
    path: string,
    method: NonNullable<LeoRequestOptions['method']>,
    body: unknown,
    options: LeoAppRequestOptions
  ): Promise<T> {
    const { cacheTtl, query, params, signal, responseType } = options
    const run = async () => {
      try {
        return await send<T>(toPath(path), { method, body, query: query ?? params, signal, responseType })
      } catch (err) {
        throw withPermissionName(err)
      }
    }
    if (method === 'GET') {
      if (!cacheTtl || responseType === 'blob') return run()
      return cachedRequest(cacheKey(path, (query ?? params ?? {}) as Record<string, unknown>), cacheTtl, run)
    }
    const result = await run()
    if (!import.meta.server) invalidateCaches()
    return result
  }

  return {
    get: <T>(path: string, options: LeoAppRequestOptions = {}) => request<T>(path, 'GET', undefined, options),
    post: <T>(path: string, body?: unknown, options: LeoAppRequestOptions = {}) => request<T>(path, 'POST', body, options),
    patch: <T>(path: string, body?: unknown, options: LeoAppRequestOptions = {}) => request<T>(path, 'PATCH', body, options),
    put: <T>(path: string, body?: unknown, options: LeoAppRequestOptions = {}) => request<T>(path, 'PUT', body, options),
    delete: <T>(path: string, options: LeoAppRequestOptions = {}) => request<T>(path, 'DELETE', undefined, options)
  }
}
