import { createLeoAppApi } from '../lib/leoAppApi'
import { toLeoPath } from '../lib/leoPaths'

/**
 * Cliente HTTP único de las apps: `get/post/patch/put/delete` contra la API de
 * la app (`NUXT_PUBLIC_API_BASE`, que debe colgar de `NUXT_PUBLIC_LEO_API_BASE`),
 * firmado por `useLeoApi`. Lanza `LeoApiError` (muéstralo con `leoErrorMessage`).
 * `{ cacheTtl }` cachea un GET; las mutaciones invalidan la caché.
 */
export function useLeoAppApi() {
  const { apiBase, leo } = useRuntimeConfig().public as { apiBase?: string, leo: { apiBase: string } }
  if (!apiBase) throw new Error('Falta NUXT_PUBLIC_API_BASE.')
  return createLeoAppApi(useLeoApi(), path => toLeoPath(apiBase, leo.apiBase, path))
}
