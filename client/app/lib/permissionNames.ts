/**
 * Nombres legibles de los permisos (tags) para mensajes al usuario
 * ("No tienes permiso para: …"). Cada app registra los suyos una vez (p. ej.
 * en un plugin) con `registerPermissionNames`.
 */
const NAMES = new Map<string, string>()

export function registerPermissionNames(names: Record<string, string>): void {
  for (const [tag, name] of Object.entries(names)) NAMES.set(tag, name)
}

export function permissionName(tag: string | undefined | null): string | null {
  return (tag && NAMES.get(tag)) || null
}

/** Detalle de un 403 `forbidden`: un tag (`action`) o varios alternativos (`any_of`). */
export interface ForbiddenDetails {
  action?: string
  any_of?: string[]
}

/**
 * Mensaje de un 403 `forbidden`: nombra el permiso que falta si se conoce
 * ("No tienes permiso para: X"; con alternativas, "X o Y"); si no, el de respaldo.
 */
export function forbiddenMessage(details: ForbiddenDetails | null | undefined, fallback: string): string {
  const tags = details?.any_of?.length ? details.any_of : details?.action ? [details.action] : []
  const names = [...new Set(tags.map(tag => permissionName(tag)).filter((n): n is string => !!n))]
  return names.length ? `No tienes permiso para: ${names.join(' o ')}` : fallback
}
