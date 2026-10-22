/**
 * Ruta para el transporte de leo-client. Éste concatena `NUXT_PUBLIC_LEO_API_BASE`
 * (el backend, sin `/api/v1`) con la ruta; la API de la app cuelga de
 * `NUXT_PUBLIC_API_BASE` (`.../api/v1`). Se deriva el prefijo de la diferencia
 * entre ambas para mantener UNA sola configuración de la URL del backend.
 */
export function toLeoPath(apiBase: string, leoApiBase: string, path: string): string {
  const api = apiBase.replace(/\/+$/, '')
  const leo = leoApiBase.replace(/\/+$/, '')
  if (!api.startsWith(leo)) {
    throw new Error('NUXT_PUBLIC_API_BASE debe colgar de NUXT_PUBLIC_LEO_API_BASE.')
  }
  return api.slice(leo.length) + (path.startsWith('/') ? path : `/${path}`)
}
