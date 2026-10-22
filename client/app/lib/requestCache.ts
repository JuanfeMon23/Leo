/**
 * Vigencia de las lecturas de la API en el navegador: un dato guardado sirve
 * mientras no venza su TTL y no haya habido una mutación después de pedirlo.
 * Toda mutación exitosa de `useLeoAppApi` llama a `invalidateCaches()`.
 */

/** TTL de un listado paginado (30 s). */
export const LIST_CACHE_TTL = 30_000
/** TTL de un catálogo para selects/modales (5 min). */
export const CATALOG_CACHE_TTL = 300_000

/** Sello de una lectura: hora y época de INICIO de la petición. */
export interface CacheStamp { at: number, epoch: number }

let epoch = 0

export function stampCache(): CacheStamp {
  return { at: Date.now(), epoch }
}

/** Marca como viejo todo lo pedido hasta ahora (se llama tras una mutación). */
export function invalidateCaches() {
  epoch++
}

/** ¿Sigue vigente una lectura sellada? No si venció el TTL o hubo una mutación después. */
export function isCacheFresh(stamp: CacheStamp, ttl: number): boolean {
  return stamp.epoch === epoch && Date.now() - stamp.at < ttl
}

/** Clave estable de un recurso + parámetros: ignora `undefined`/`null`/`''` y el orden de las claves. */
export function cacheKey(resource: string, params: Record<string, unknown> = {}): string {
  const entries = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
  if (!entries.length) return resource
  return `${resource}?${JSON.stringify(Object.fromEntries(entries))}`
}

const cache = new Map<string, { stamp: CacheStamp, promise: Promise<unknown> }>()

/**
 * Lectura cacheada: una sola carga para llamadas simultáneas, vigente según
 * `isCacheFresh`. Los errores no se guardan. En el servidor siempre carga
 * (la caché se compartiría entre usuarios).
 */
export function cachedRequest<T>(key: string, ttl: number, loader: () => Promise<T>): Promise<T> {
  if (import.meta.server) return loader()
  const hit = cache.get(key)
  if (hit && isCacheFresh(hit.stamp, ttl)) return hit.promise as Promise<T>
  const entry = { stamp: stampCache(), promise: loader() }
  cache.set(key, entry)
  entry.promise.catch(() => {
    if (cache.get(key) === entry) cache.delete(key)
  })
  return entry.promise as Promise<T>
}
