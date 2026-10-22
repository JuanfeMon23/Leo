// API pública para apps (auto-importada): rutas, nombres de permisos y caché.
export { toLeoPath } from '../lib/leoPaths'
export { forbiddenMessage, permissionName, registerPermissionNames } from '../lib/permissionNames'
export type { ForbiddenDetails } from '../lib/permissionNames'
export { CATALOG_CACHE_TTL, LIST_CACHE_TTL, cacheKey, cachedRequest, invalidateCaches, isCacheFresh, stampCache } from '../lib/requestCache'
export type { LeoAppRequestOptions } from '../lib/leoAppApi'
