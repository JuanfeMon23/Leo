/**
 * Regla de permisos por tag de acción (`<app>.<modulo>.<accion>`): coincidencia
 * exacta, sin comodines ni prefijos. Niega por defecto (sin permisos, sin
 * tags o con una lista vacía → false).
 */
export type LeoTagMode = 'all' | 'any'

export function hasPermission(
  permissions: readonly string[] | ReadonlySet<string> | null | undefined,
  tags: string | readonly string[],
  mode: LeoTagMode = 'all'
): boolean {
  if (!permissions) return false
  const list = (typeof tags === 'string' ? [tags] : [...tags]).filter(Boolean)
  if (list.length === 0) return false
  const granted = permissions instanceof Set ? permissions : new Set(permissions as readonly string[])
  return mode === 'any' ? list.some(tag => granted.has(tag)) : list.every(tag => granted.has(tag))
}
